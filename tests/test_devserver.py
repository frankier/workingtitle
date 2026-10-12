"""Headless integration contracts, independent of desktop and compilers."""

import subprocess
import sys
from types import SimpleNamespace

import pytest

from workingtitle.devserver import (
    AssetPlan,
    NpmBuild,
    PythonBuild,
    ReloadSpec,
    run_server,
)
from workingtitle.devserver import assets
from workingtitle.devserver.__main__ import main


def test_imports_are_lazy():
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
import workingtitle.devserver
assert not {'uvicorn', 'watchfiles', 'webview', 'PyInstaller', 'bokeh',
            'workingtitle.desktop'} & sys.modules.keys()
""",
        ],
        check=True,
    )


@pytest.mark.parametrize("factory", [False, True])
def test_build_before_app_import(tmp_path, monkeypatch, factory):
    import uvicorn

    (tmp_path / "webexample.py").write_text("""
from pathlib import Path
assert Path(__file__).with_name('index.js').is_file()
assert Path(__file__).with_name('index.css').is_file()
async def app(scope, receive, send): pass
def create_app(): return app
""")
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "package-lock.json").write_text("{}")
    plan = AssetPlan(tmp_path, (NpmBuild("web", (), ("index.js", "index.css")),))

    def npm(command, **kwargs):
        assert "webexample" not in sys.modules
        if command[1] == "ci":
            (tmp_path / "node_modules").mkdir()
            (tmp_path / "node_modules/.package-lock.json").touch()
        else:
            for output in ("index.js", "index.css"):
                (tmp_path / output).write_text("built")

    def serve(self, sockets):
        self.config.load()  # Real Uvicorn import/factory resolution.
        assert self.config.loaded_app is not None
        assert self.config.root_path == "/prefix"

    monkeypatch.setattr(assets.subprocess, "run", npm)
    monkeypatch.setattr(uvicorn.Server, "run", serve)
    sys.modules.pop("webexample", None)
    try:
        run_server(
            "webexample:create_app" if factory else "webexample:app",
            factory=factory,
            assets=plan,
            port=0,
            root_path="/prefix",
        )
    finally:
        sys.modules.pop("webexample", None)


def test_failed_start_never_imports_app(monkeypatch):
    import uvicorn

    def fail():
        raise RuntimeError("build failed")

    monkeypatch.setattr(uvicorn, "Config", lambda *a, **kw: pytest.fail("app config"))
    with pytest.raises(RuntimeError, match="build failed"):
        run_server("absent:app", assets=SimpleNamespace(ensure_built=fail))


def test_reload_failure_keeps_child_and_recovers(tmp_path, monkeypatch, capsys):
    import uvicorn.supervisors

    events = []

    class Reload:
        def __init__(self, config, target, sockets):
            self.watch_filter = lambda path: path.suffix == ".py"

        def restart(self):
            events.append("restart")

        def run(self):
            assert self.watch_filter(tmp_path / "templates/a.html")
            for name in (
                "out.js",
                ".workingtitle-build/web.json",
                ".venv-local/test.py",
                "results/a.py",
                "ray/a.py",
            ):
                assert not self.watch_filter(tmp_path / name)
            self.restart()
            self.restart()

    attempts = []

    def build(context):
        attempts.append("build")
        if len(attempts) == 2:
            raise RuntimeError("bad template")
        (tmp_path / "out.js").write_text("built")

    plan = AssetPlan(
        tmp_path,
        (PythonBuild("web", ("templates/**",), ("out.js",), "compiler:build"),),
    )
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates/a.html").write_text("template")
    # Force each check to build to exercise failure followed by recovery.
    original = AssetPlan.ensure_built
    monkeypatch.setattr(
        AssetPlan, "ensure_built", lambda self: original(self, force=True)
    )
    monkeypatch.setattr(assets, "import_object", lambda ref: build)
    monkeypatch.setattr(uvicorn.supervisors, "ChangeReload", Reload)
    run_server(
        "absent:app",
        port=0,
        assets=plan,
        reload=ReloadSpec(excludes=(".venv-local", "results", "ray")),
    )
    assert attempts == ["build", "build", "build"]
    assert events == ["restart"]
    assert "bad template" in capsys.readouterr().err


def test_ordered_outputs_and_compiler_version(tmp_path, monkeypatch):
    from dataclasses import replace

    (tmp_path / "model.ts").write_text("first")
    steps = (
        PythonBuild(
            "compile",
            ("*.ts",),
            ("bundle.js",),
            "compiler:compile",
            cache_key="bokeh-1",
        ),
        PythonBuild("pack", ("bundle.js",), ("package.js",), "compiler:pack"),
    )
    plan = AssetPlan(tmp_path, steps)
    calls = []

    def resolve(ref):
        def build(context):
            calls.append(context.name)
            if context.name == "compile":
                (tmp_path / "bundle.js").write_text((tmp_path / "model.ts").read_text())
            else:
                (tmp_path / "package.js").write_text(
                    (tmp_path / "bundle.js").read_text()
                )

        return build

    monkeypatch.setattr(assets, "import_object", resolve)
    plan.ensure_built()
    plan.ensure_built()
    (tmp_path / "model.ts").write_text("second")
    plan.ensure_built()
    plan = replace(plan, steps=(replace(steps[0], cache_key="bokeh-2"), steps[1]))
    plan.ensure_built()
    assert calls == ["compile", "pack", "compile", "pack", "compile"]
    assert not plan.is_input(tmp_path / "bundle.js")  # no filesystem reload loop


def test_forced_fallback_is_retryable(tmp_path, monkeypatch):
    from workingtitle.devserver import BuildUnavailable

    step = PythonBuild("web", (), ("out.js",), "compiler:build")
    plan = AssetPlan(tmp_path, (step,))
    monkeypatch.setattr(
        assets,
        "import_object",
        lambda ref: lambda: (tmp_path / "out.js").write_text("ok"),
    )
    plan.ensure_built()

    def unavailable():
        raise BuildUnavailable("no compiler")

    monkeypatch.setattr(assets, "import_object", lambda ref: unavailable)
    with pytest.warns(UserWarning, match="existing assets"):
        plan.ensure_built(force=True)
    assert not (tmp_path / plan.cache_dir / "web.json").exists()
    with pytest.raises(BuildUnavailable):
        plan.ensure_built(strict=True)


def test_strict_build_cli_does_not_import_web_app(tmp_path, monkeypatch):
    (tmp_path / "buildplan.py").write_text(f"""
from pathlib import Path
from workingtitle.devserver import AssetPlan, PythonBuild
assert 'eager_web_app' not in __import__('sys').modules
def build(context):
    assert context.strict
    (context.root / 'out.js').write_text('built')
ASSETS = AssetPlan(Path({str(tmp_path)!r}),
    (PythonBuild('web', (), ('out.js',), 'buildplan:build'),))
""")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        main(["buildplan:ASSETS"])
        assert (tmp_path / "out.js").read_text() == "built"
    finally:
        sys.modules.pop("buildplan", None)


def test_concurrent_build_guard_and_installed_validation(tmp_path, monkeypatch):
    plan = AssetPlan(tmp_path, (PythonBuild("web", (), ("out.js",), "absent:build"),))
    cache = tmp_path / plan.cache_dir
    cache.mkdir()
    (cache / "build.lock").touch()
    with pytest.raises(RuntimeError, match="another asset build"):
        plan.ensure_built()
    installed = AssetPlan(tmp_path, plan.steps, source=False)
    monkeypatch.setattr(
        assets, "import_object", lambda ref: pytest.fail("compiler import")
    )
    monkeypatch.setattr(assets.subprocess, "run", lambda *a, **kw: pytest.fail("npm"))
    with pytest.raises(RuntimeError, match="missing built assets"):
        installed.ensure_built(strict=True)
    (tmp_path / "out.js").write_text("shipped")
    installed.ensure_built(strict=True)
    assert list(cache.iterdir()) == [cache / "build.lock"]


def test_npm_inputs_and_custom_cwd(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    for name in ("package.json", "package-lock.json", "template.html"):
        (frontend / name).write_text("one")
    plan = AssetPlan(
        tmp_path,
        (
            NpmBuild(
                "web",
                ("frontend/*.html",),
                ("out.js",),
                cwd="frontend",
                script="assets",
                install_args=("install",),
            ),
        ),
    )
    commands = []

    def run(command, *, cwd, check):
        assert cwd == frontend
        commands.append(command[1:])
        if command[1] == "install":
            (frontend / "node_modules").mkdir(exist_ok=True)
            (frontend / "node_modules/.package-lock.json").touch()
        else:
            (tmp_path / "out.js").write_text("built")

    monkeypatch.setattr(assets.subprocess, "run", run)
    plan.ensure_built()
    for name in ("template.html", "new.html", "package.json", "package-lock.json"):
        (frontend / name).write_text("changed")
        assert plan.is_input(frontend / name)
        plan.ensure_built()
    (frontend / "new.html").rename(frontend / "renamed.html")
    plan.ensure_built()
    (frontend / "renamed.html").unlink()
    plan.ensure_built()
    (tmp_path / "out.js").unlink()
    plan.ensure_built()
    assert commands.count(["install"]) == 3
    assert commands.count(["run", "assets"]) == 8


def test_real_npm_headless_example(tmp_path):
    import shutil

    if shutil.which("npm") is None:
        pytest.skip("example integration requires npm")
    example = (
        __import__("pathlib").Path(__file__).resolve().parents[1] / "examples/headless"
    )
    shutil.copytree(
        example,
        tmp_path / "example",
        ignore=shutil.ignore_patterns(
            "static", ".workingtitle-build", "__pycache__", "node_modules"
        ),
    )
    root = tmp_path / "example"
    assert not (root / "static/index.js").exists()
    assert not (root / "static/index.css").exists()
    code = """
from web_assets import ASSETS
ASSETS.ensure_built(strict=True)
import app
assert app.app is not None
"""
    import os

    env = {**os.environ, "npm_config_cache": str(tmp_path / "npm-cache")}
    subprocess.run(
        [sys.executable, "-c", code], cwd=root, env=env, check=True, capture_output=True
    )
    assert (root / "static/index.js").read_text() == (
        root / "frontend/index.js"
    ).read_text()
    assert (root / "static/index.css").read_text() == (
        root / "frontend/index.css"
    ).read_text()


def test_broad_input_glob_does_not_track_own_outputs(tmp_path, monkeypatch):
    calls = []
    plan = AssetPlan(
        tmp_path, (PythonBuild("web", ("**/*",), ("out.js",), "compiler:build"),)
    )

    def build():
        calls.append("build")
        (tmp_path / "out.js").write_text("generated")

    monkeypatch.setattr(assets, "import_object", lambda ref: build)
    plan.ensure_built()
    plan.ensure_built()
    assert calls == ["build"]
