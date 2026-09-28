"""Ordered, incremental frontend builds shared by startup and packaging."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from .runtime import import_object


@dataclass(frozen=True)
class NpmBuild:
    name: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    cwd: str = "."
    script: str = "build"
    install_args: tuple[str, ...] = ("ci", "--ignore-scripts")


@dataclass(frozen=True)
class PythonBuild:
    """A lazy zero-argument callable; failures must raise an exception.

    Use an app-owned wrapper when the compiler needs flags or validation.
    """

    name: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    action: str


@dataclass(frozen=True)
class AssetPlan:
    """Paths and globs are relative to an explicit project/resource root.

    Source mode builds stale assets. With ``source=False`` (or when frozen),
    only output presence is checked. Installed wheels should use source=False.
    No compiler imports or npm calls are made in that mode.
    """

    root: Path
    steps: tuple[NpmBuild | PythonBuild, ...]
    source: bool = True
    cache_dir: str = ".desktop-build"
    excludes: tuple[str, ...] = (
        "node_modules",
        ".venv",
        "__pycache__",
        ".git",
        "build",
        "dist",
    )

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root).resolve())
        names = [step.name for step in self.steps]
        if len(names) != len(set(names)):
            raise ValueError("asset step names must be unique")
        for step in self.steps:
            if not step.name or not all(c.isalnum() or c in "-_" for c in step.name):
                raise ValueError(
                    "asset step names must contain only letters, digits, - or _"
                )
            if not step.outputs:
                raise ValueError(f"asset step {step.name!r} needs declared outputs")

    def _patterns(self, step):
        patterns = list(step.inputs)
        if isinstance(step, NpmBuild):
            patterns += [
                str(Path(step.cwd) / name)
                for name in ("package.json", "package-lock.json")
            ]
        return patterns

    def is_ignored(self, path):
        path = Path(path)
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            return False
        return (
            any(part in self.excludes for part in relative.parts)
            or path.is_relative_to(self.root / self.cache_dir)
            or any(
                path == self.root / output for s in self.steps for output in s.outputs
            )
        )

    def is_input(self, path):
        """Match even deleted or newly created files, without scanning the tree."""
        try:
            relative = Path(path).relative_to(self.root)
        except ValueError:
            return False
        if self.is_ignored(path):
            return False

        def matches(parts, pattern):
            if not pattern:
                return not parts
            if pattern[0] == "**":
                return matches(parts, pattern[1:]) or bool(
                    parts and matches(parts[1:], pattern)
                )
            return bool(
                parts
                and fnmatchcase(parts[0], pattern[0])
                and matches(parts[1:], pattern[1:])
            )

        return any(
            matches(relative.parts, Path(pattern).parts)
            for step in self.steps
            for pattern in self._patterns(step)
        )

    def watch_filter(self, base_filter):
        """Extend Uvicorn's Python filter with the exact asset input globs."""
        return lambda path: (
            not self.is_ignored(path) and (self.is_input(path) or base_filter(path))
        )

    def _inputs(self, step):
        files = set()
        for pattern in self._patterns(step):
            # pathlib on Python 3.10 treats a trailing ** as directories only.
            if pattern.endswith("/**"):
                pattern += "/*"
            for path in self.root.glob(pattern):
                if path.is_file() and not self.is_ignored(path):
                    files.add(path)
        return sorted(files)

    def _fingerprint(self, step):
        digest = hashlib.sha256(repr(step).encode())
        for path in self._inputs(step):
            digest.update(path.relative_to(self.root).as_posix().encode())
            digest.update(b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        return digest.hexdigest()

    def _validate(self, step):
        missing = [path for path in step.outputs if not (self.root / path).is_file()]
        if missing:
            raise RuntimeError(
                f"{step.name}: missing built assets: {', '.join(missing)}"
            )

    def ensure_built(self, *, force=False):
        if not self.source or getattr(sys, "frozen", False):
            for step in self.steps:
                self._validate(step)
            return
        for step in self.steps:
            fingerprint = self._fingerprint(step)
            stamp = self.root / self.cache_dir / f"{step.name}.json"
            try:
                previous = json.loads(stamp.read_text())
            except (OSError, ValueError):
                previous = None
            present = all((self.root / path).is_file() for path in step.outputs)
            if not force and present and previous == fingerprint:
                continue
            if isinstance(step, NpmBuild):
                self._npm_build(step)
            else:
                import_object(step.action)()
            self._validate(step)
            # Record the inputs observed before compilation: edits made while
            # building must still invalidate the result on the next check.
            stamp.parent.mkdir(parents=True, exist_ok=True)
            stamp.write_text(json.dumps(fingerprint))

    def _npm_build(self, step):
        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        cwd = self.root / step.cwd
        lock = cwd / "package-lock.json"
        manifest = cwd / "package.json"
        dependency_hash = hashlib.sha256(
            manifest.read_bytes() + lock.read_bytes()
        ).hexdigest()
        stamp = self.root / self.cache_dir / f"{step.name}-npm.txt"
        installed = cwd / "node_modules/.package-lock.json"
        current = stamp.read_text() if stamp.exists() else None
        if not installed.is_file() or current != dependency_hash:
            subprocess.run([npm, *step.install_args], cwd=cwd, check=True)
            stamp.parent.mkdir(parents=True, exist_ok=True)
            stamp.write_text(dependency_hash)
        subprocess.run([npm, "run", step.script], cwd=cwd, check=True)
