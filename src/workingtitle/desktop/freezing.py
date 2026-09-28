"""Declarative helpers called from a small application-owned PyInstaller spec.

PyInstaller imports stay inside build functions. Domain-library collection
recipes belong to the application, not to this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
import shutil
import sys
from typing import Callable, Mapping, Any

from .runtime import AppSpec


@dataclass(frozen=True)
class PackageData:
    package: str
    includes: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Submodules:
    package: str
    filter: tuple[str, ...] | Callable[[str], bool] = ()


@dataclass(frozen=True)
class BundleSpec:
    app: AppSpec
    entrypoint: str
    root: Path
    packages: tuple[PackageData, ...] = ()
    metadata: tuple[str, ...] = ()
    submodules: tuple[Submodules, ...] = ()
    hiddenimports: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    runtime_hooks: tuple[str, ...] = ()
    hookspath: tuple[str, ...] = ()
    pathex: tuple[str, ...] = ("src",)
    datas: tuple[tuple[str, str], ...] = ()
    binaries: tuple[tuple[str, str], ...] = ()
    matplotlib: bool = False
    console: bool = True
    bundle_identifier: str | None = None
    version: str = "0.1.0"
    info_plist: Mapping[str, Any] = field(default_factory=dict)
    # Source files relative to root, copied beside the EXE after COLLECT.
    adjacent_files: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    data_filter: Callable | None = None


def platform_options(app: AppSpec, platform: str | None = None):
    """Use the runtime's native-platform policy when collecting GUI backends."""
    platform = platform or sys.platform
    hidden = []
    excludes = []
    if platform not in app.native_platforms:
        excludes += ["webview", "gi", "pythonnet", "clr"]
    else:
        if platform not in ("win32", "darwin"):
            raise ValueError(f"no native packaging recipe for {platform}")
        excludes += [
            "webview.platforms.gtk",
            "webview.platforms.qt",
            "webview.platforms.android",
        ]
        hidden += ["webview"]
        hidden += (
            ["webview.platforms.cocoa"]
            if platform == "darwin"
            else ["webview.platforms.edgechromium", "webview.platforms.winforms"]
        )
    return hidden, excludes


def _not_excluded(prefixes: tuple[str, ...], name: str) -> bool:
    """Whether ``name`` lies outside every excluded module prefix."""
    return not any(name == p or name.startswith(p + ".") for p in prefixes)


def analysis_options(spec: BundleSpec):
    """Collect Analysis arguments; call after building frontend assets."""
    from PyInstaller.utils.hooks import (
        collect_data_files,
        collect_submodules,
        copy_metadata,
    )

    root = Path(spec.root).resolve()
    hidden, excludes = platform_options(spec.app)
    hidden += collect_submodules("uvicorn")
    hidden += [
        spec.app.factory.split(":", 1)[0],
        "websockets",
        "anyio._backends._asyncio",
        "encodings.idna",
    ]
    hidden += list(spec.hiddenimports)
    excludes += list(spec.excludes)
    datas = [(str(root / src), dest) for src, dest in spec.datas]
    for package in spec.packages:
        options = {"excludes": list(package.excludes)}
        if package.includes:
            options["includes"] = list(package.includes)
        datas += collect_data_files(package.package, **options)
    for package in spec.metadata:
        datas += copy_metadata(package)
    for group in spec.submodules:
        if isinstance(group.filter, tuple):
            predicate = partial(_not_excluded, group.filter)
        else:
            predicate = group.filter
        hidden += collect_submodules(group.package, filter=predicate)
    hooks = [str(root / path) for path in spec.runtime_hooks]
    if spec.matplotlib:
        datas += collect_data_files("matplotlib")
        datas += copy_metadata("matplotlib")
        hooks.insert(0, str(Path(__file__).parent / "hooks" / "rthook_mplconfig.py"))
    return {
        "pathex": [str(root / path) for path in spec.pathex],
        "datas": datas,
        "binaries": [(str(root / src), dest) for src, dest in spec.binaries],
        "hiddenimports": list(dict.fromkeys(hidden)),
        "excludes": list(dict.fromkeys(excludes)),
        "hookspath": [str(root / path) for path in spec.hookspath],
        "runtime_hooks": hooks,
        "noarchive": False,
    }


def build_bundle(spec: BundleSpec, namespace: Mapping[str, Any], *, assets=None):
    """Build onedir (plus .app on macOS) using the spec's PyInstaller globals.

    Call ``build_bundle(recipe, globals(), assets=plan)`` inside a .spec file.
    Returns the COLLECT or BUNDLE object. Asset failures abort packaging: the
    plan rebuilds with ``force=True, strict=True`` so it cannot fall back to
    stale outputs the way development startup may.
    """
    if assets is not None:
        assets.ensure_built(force=True, strict=True)
    root = Path(spec.root).resolve()
    analysis = namespace["Analysis"](
        [str(root / spec.entrypoint)], **analysis_options(spec)
    )
    if spec.data_filter is not None:
        analysis.datas = [entry for entry in analysis.datas if spec.data_filter(entry)]
    pyz = namespace["PYZ"](analysis.pure)
    exe = namespace["EXE"](
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=spec.app.name,
        debug=False,
        strip=False,
        upx=False,
        console=spec.console,
    )
    collection = namespace["COLLECT"](
        exe,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        name=spec.app.name,
    )
    for path in spec.adjacent_files.get(sys.platform, ()):
        shutil.copyfile(root / path, Path(collection.name) / Path(path).name)
    if sys.platform == "darwin":
        return namespace["BUNDLE"](
            collection,
            name=f"{spec.app.title}.app",
            bundle_identifier=spec.bundle_identifier,
            info_plist={
                "NSHighResolutionCapable": True,
                "LSMinimumSystemVersion": "11.0",
                "CFBundleShortVersionString": spec.version,
                **spec.info_plist,
            },
        )
    return collection
