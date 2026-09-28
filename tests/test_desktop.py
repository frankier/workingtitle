import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
from types import SimpleNamespace
import urllib.request

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from workingtitle.desktop import (
    AppSpec,
    AssetPlan,
    DesktopSession,
    NpmBuild,
    PythonBuild,
    ServerThread,
    bind_socket,
    run_cli,
)
from workingtitle.desktop import assets, freezing, runtime


def app_spec(**kwargs):
    return AppSpec("example", "Example", "example.app:create_app", **kwargs)


def test_import_without_optional_dependencies():
    code = """
import sys
import workingtitle.desktop
import workingtitle.desktop.freezing
assert not {'uvicorn', 'webview', 'PyInstaller', 'watchfiles'} & sys.modules.keys()
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_server_lifecycle_and_socket_ownership():
    async def hello(request):
        return PlainTextResponse("hello")

    app = Starlette(routes=[Route("/", hello)])
    sock = bind_socket()
    with ServerThread(app, sock) as server:
        with urllib.request.urlopen(server.url, timeout=5) as response:
            assert response.read() == b"hello"
    assert sock.fileno() == -1
    assert not server.thread.is_alive()


def test_window_creation_failure_stops_server(monkeypatch):
    calls = []

    class Server:
        url = "http://localhost/"

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            calls.append("start")
            return self

        def __exit__(self, *args):
            calls.append("stop")

    def fail(*args, **kwargs):
        raise RuntimeError("no GUI")

    monkeypatch.setattr(runtime, "ServerThread", Server)
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace(create_window=fail))
    session = DesktopSession(app_spec())
    with pytest.raises(RuntimeError, match="no GUI"):
        session.run_window(object(), object())
    assert calls == ["start", "stop"]
    assert session.window is None


def test_native_fallback_rebinds_and_respects_no_browser(monkeypatch):
    session = DesktopSession(app_spec())
    monkeypatch.setattr(session, "native_window_supported", lambda: True)
    sockets = []

    def fail(app, sock):
        sockets.append(sock)
        sock.close()
        raise RuntimeError("backend missing")

    def browser(app, sock, *, open_browser):
        sockets.append(sock)
        assert sock.fileno() != -1
        assert not open_browser

    monkeypatch.setattr(session, "run_window", fail)
    monkeypatch.setattr(session, "run_browser", browser)
    session.run(object(), open_browser=False)
    assert len(sockets) == 2 and sockets[0] is not sockets[1]
    assert all(sock.fileno() == -1 for sock in sockets)


def test_dialogs_use_the_native_window_and_return_paths(monkeypatch, tmp_path):
    calls = []

    class Window:
        def create_file_dialog(self, kind, **kwargs):
            calls.append((kind, kwargs))
            selected = kwargs.get("save_filename") and (str(tmp_path / "conf.toml"),)
            return selected or (str(tmp_path / "a"), str(tmp_path / "b"))

    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(FileDialog=SimpleNamespace(OPEN=10, FOLDER=20, SAVE=30)),
    )
    session = DesktopSession(app_spec())
    assert not session.native
    with pytest.raises(RuntimeError, match="no native window"):
        session.open_folder()

    session.window = Window()
    assert session.native
    assert session.open_folder(allow_multiple=True, directory=tmp_path) == (
        tmp_path / "a",
        tmp_path / "b",
    )
    assert session.open_file(file_types=("Data (*.txt)",)) == (
        tmp_path / "a",
        tmp_path / "b",
    )
    assert session.save_file(filename="conf.toml") == tmp_path / "conf.toml"
    assert [kind for kind, _ in calls] == [20, 10, 30]
    assert calls[0][1] == {
        "directory": str(tmp_path),
        "allow_multiple": True,
        "save_filename": "",
        "file_types": (),
    }
    assert calls[1][1]["file_types"] == ("Data (*.txt)",)
    assert calls[1][1]["directory"] == ""
    assert calls[2][1]["save_filename"] == "conf.toml"


def test_save_dialog_cancelled_returns_none(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(FileDialog=SimpleNamespace(SAVE=30)),
    )
    session = DesktopSession(app_spec())
    session.window = SimpleNamespace(create_file_dialog=lambda *args, **kwargs: None)
    assert session.save_file() is None


def test_bind_failure_closes_socket(monkeypatch):
    sock = socket.socket()
    monkeypatch.setattr(runtime.socket, "socket", lambda *args: sock)
    with pytest.raises(OverflowError):
        bind_socket(port=100000)
    assert sock.fileno() == -1


def test_cli_prepares_before_build_and_factory_and_restores_environment(monkeypatch):
    calls = []
    monkeypatch.setenv("EXAMPLE_CONFIG", "old")

    def prepare(args):
        calls.append("prepare")
        return {"EXAMPLE_CONFIG": args.config}

    def build():
        assert os.environ["EXAMPLE_CONFIG"] == "new"
        calls.append("build")

    def factory():
        assert os.environ["EXAMPLE_CONFIG"] == "new"
        calls.append("factory")
        return "app"

    def launch(app, host, port, **kwargs):
        calls.append("launch")
        assert app == "app"
        assert kwargs == {"mode": "browser", "open_browser": False}

    monkeypatch.setattr(runtime, "import_object", lambda reference: factory)
    assert (
        run_cli(
            app_spec(),
            ["--config", "new", "--no-window", "--no-browser"],
            add_arguments=lambda parser: parser.add_argument("--config"),
            prepare=prepare,
            assets=SimpleNamespace(ensure_built=build),
            session=SimpleNamespace(run=launch),
        )
        == 0
    )
    assert calls == ["prepare", "build", "factory", "launch"]
    assert os.environ["EXAMPLE_CONFIG"] == "old"


def test_smoke_bypasses_normal_config_and_reload(monkeypatch):
    monkeypatch.setattr(runtime.importlib.util, "find_spec", lambda name: None)

    def forbidden(*args):
        pytest.fail("normal preparation/factory should not run")

    monkeypatch.setattr(runtime, "import_object", forbidden)
    assert (
        run_cli(
            app_spec(),
            ["--smoke-test", "--debug"],
            prepare=forbidden,
            smoke_test=lambda args, session: 7,
        )
        == 7
    )


def test_reload_requires_watchfiles(monkeypatch, capsys):
    monkeypatch.setattr(runtime.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(SystemExit) as exc:
        run_cli(app_spec(), ["--reload"])
    assert exc.value.code == 2
    assert "desktop-dev" in capsys.readouterr().err


def test_reload_builds_before_restart_and_keeps_environment(monkeypatch):
    import uvicorn.supervisors

    events = []
    monkeypatch.setenv("EXAMPLE_DEBUG", "original")

    class Reload:
        def __init__(self, config, target, sockets):
            self.config = config
            self.watch_filter = lambda path: True

        def restart(self):
            events.append("restart")

        def run(self):
            assert self.config.app == "example.app:create_app"
            assert os.environ["EXAMPLE_DEBUG"] == "1"
            self.restart()

    monkeypatch.setattr(uvicorn.supervisors, "ChangeReload", Reload)
    plan = SimpleNamespace(
        ensure_built=lambda: events.append("build"),
        root=Path.cwd(),
        watch_filter=lambda base: base,
    )
    run_cli(
        app_spec(debug_env_var="EXAMPLE_DEBUG"),
        ["--debug", "--no-browser"],
        assets=plan,
    )
    assert events == ["build", "build", "restart"]
    assert os.environ["EXAMPLE_DEBUG"] == "original"


def python_plan(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.ts").write_text("one")
    step = PythonBuild("frontend", ("src/**/*.ts",), ("out.js",), "example.build:build")
    return AssetPlan(tmp_path, (step,))


def test_builds_detect_changes_deletions_and_missing_outputs(tmp_path, monkeypatch):
    plan = python_plan(tmp_path)
    calls = []

    def build():
        calls.append("build")
        (tmp_path / "out.js").write_text("compiled")

    monkeypatch.setattr(assets, "import_object", lambda reference: build)
    plan.ensure_built()
    plan.ensure_built()
    assert calls == ["build"]
    (tmp_path / "src/a.ts").write_text("two")
    plan.ensure_built()
    (tmp_path / "src/a.ts").unlink()
    plan.ensure_built()
    (tmp_path / "out.js").unlink()
    plan.ensure_built()
    assert len(calls) == 4


def test_failed_build_is_retried(tmp_path, monkeypatch):
    plan = python_plan(tmp_path)
    calls = []

    def build():
        calls.append("build")
        raise RuntimeError("bad source")

    monkeypatch.setattr(assets, "import_object", lambda reference: build)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="bad source"):
            plan.ensure_built()
    assert len(calls) == 2
    assert not (tmp_path / ".desktop-build/frontend.json").exists()


def test_python_action_receives_build_context(tmp_path, monkeypatch):
    plan = python_plan(tmp_path)
    seen = []

    def build(context):
        seen.append(context)
        (tmp_path / "out.js").write_text("compiled")

    monkeypatch.setattr(assets, "import_object", lambda reference: build)
    plan.ensure_built(force=True, strict=True)
    assert [(c.name, c.root, c.force, c.strict) for c in seen] == [
        ("frontend", plan.root, True, True)
    ]


def test_fallback_to_stale_assets_is_retried(tmp_path, monkeypatch):
    plan = python_plan(tmp_path)
    (tmp_path / "out.js").write_text("stale")
    calls = []

    def build(context):
        calls.append(context.strict)
        if len(calls) == 1:
            raise assets.BuildUnavailable("cannot compile")
        (tmp_path / "out.js").write_text("fresh")

    monkeypatch.setattr(assets, "import_object", lambda reference: build)
    plan.ensure_built()
    assert (tmp_path / "out.js").read_text() == "stale"
    # A fallback is not stamped, so the next call retries the step.
    assert not (tmp_path / ".desktop-build/frontend.json").exists()
    plan.ensure_built()
    assert (tmp_path / "out.js").read_text() == "fresh"
    assert (tmp_path / ".desktop-build/frontend.json").is_file()
    assert calls == [False, False]


def test_strict_fallback_raises_and_is_not_stamped(tmp_path, monkeypatch):
    plan = python_plan(tmp_path)
    (tmp_path / "out.js").write_text("stale")

    def build(context):
        assert context.strict
        raise assets.BuildUnavailable("stale only")

    monkeypatch.setattr(assets, "import_object", lambda reference: build)
    with pytest.raises(assets.BuildUnavailable, match="stale only"):
        plan.ensure_built(force=True, strict=True)
    assert not (tmp_path / ".desktop-build/frontend.json").exists()


def test_fallback_without_stale_outputs_raises(tmp_path, monkeypatch):
    plan = python_plan(tmp_path)

    def build(context):
        raise assets.BuildUnavailable("nothing built")

    monkeypatch.setattr(assets, "import_object", lambda reference: build)
    with pytest.raises(assets.BuildUnavailable, match="nothing built"):
        plan.ensure_built()


@pytest.mark.parametrize("frozen", [False, True])
def test_installed_or_frozen_only_validates_outputs(tmp_path, monkeypatch, frozen):
    plan = python_plan(tmp_path)
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    plan = AssetPlan(tmp_path, plan.steps, source=frozen)
    monkeypatch.setattr(assets, "import_object", lambda ref: pytest.fail("no compiler"))
    with pytest.raises(RuntimeError, match="missing built assets"):
        plan.ensure_built(force=True)
    (tmp_path / "out.js").write_text("shipped")
    plan.ensure_built(force=True)


def test_npm_reinstalls_when_lock_changes(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "package-lock.json").write_text("lock one")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.ts").write_text("code")
    plan = AssetPlan(tmp_path, (NpmBuild("web", ("src/**",), ("out.js",)),))
    calls = []

    def run(command, *, cwd, check):
        calls.append(command[1:])
        assert cwd == tmp_path and check
        if command[1] == "ci":
            (tmp_path / "node_modules").mkdir(exist_ok=True)
            (tmp_path / "node_modules/.package-lock.json").touch()
        else:
            (tmp_path / "out.js").write_text("compiled")

    monkeypatch.setattr(assets.subprocess, "run", run)
    plan.ensure_built()
    plan.ensure_built()
    (tmp_path / "src/a.ts").write_text("new source")
    plan.ensure_built()
    (tmp_path / "package-lock.json").write_text("lock two")
    plan.ensure_built()
    assert calls == [
        ["ci", "--ignore-scripts"],
        ["run", "build"],
        ["run", "build"],
        ["ci", "--ignore-scripts"],
        ["run", "build"],
    ]


def test_asset_reload_filter(tmp_path):
    from uvicorn import Config
    from uvicorn.supervisors.watchfilesreload import FileFilter

    for directory in (
        "src/js/nested",
        "src/css",
        "templates",
        "node_modules",
        "src/ext/node_modules",
    ):
        (tmp_path / directory).mkdir(parents=True)
    plan = AssetPlan(
        tmp_path,
        (
            NpmBuild(
                "web",
                ("src/js/**", "src/css/**", "templates/**"),
                ("src/js/generated.js",),
            ),
        ),
    )
    config = Config(
        "example:create_app",
        reload=True,
        reload_dirs=[str(tmp_path)],
    )
    accepts = plan.watch_filter(FileFilter(config))
    for name in (
        "src/js/a.ts",
        "src/js/nested/b.ts",
        "src/css/index.css",
        "templates/base.html",
        "package-lock.json",
    ):
        assert accepts(tmp_path / name), name
    for name in (
        "src/js/generated.js",
        "node_modules/a.ts",
        "src/ext/node_modules/a.ts",
        ".desktop-build/web.json",
    ):
        assert not accepts(tmp_path / name), name


@pytest.mark.parametrize(
    "platform, expected",
    [("linux", None), ("darwin", "cocoa"), ("win32", "edgechromium")],
)
def test_packaging_matches_runtime_platform_policy(platform, expected):
    hidden, excluded = freezing.platform_options(app_spec(), platform)
    if expected:
        assert f"webview.platforms.{expected}" in hidden
    else:
        assert "webview" in excluded


def test_bundle_build_order_filter_and_adjacent_files(tmp_path, monkeypatch):
    events = []
    (tmp_path / "dist").mkdir()
    (tmp_path / "example.exe.config").write_text("config")
    analysis = SimpleNamespace(
        pure=[], scripts=[], binaries=[], datas=[("keep",), ("drop",)]
    )

    def analyze(scripts, **kwargs):
        events.append("analysis")
        assert scripts == [str(tmp_path / "main.py")]
        return analysis

    monkeypatch.setattr(freezing, "analysis_options", lambda spec: {})
    namespace = {
        "Analysis": analyze,
        "PYZ": lambda pure: None,
        "EXE": lambda *a, **kw: None,
        "COLLECT": lambda *a, **kw: SimpleNamespace(name=str(tmp_path / "dist")),
    }
    spec = freezing.BundleSpec(
        app_spec(),
        "main.py",
        tmp_path,
        data_filter=lambda entry: entry[0] == "keep",
        adjacent_files={sys.platform: ("example.exe.config",)},
    )
    freezing.build_bundle(
        spec,
        namespace,
        assets=SimpleNamespace(ensure_built=lambda **kw: events.append(("build", kw))),
    )
    assert events == [("build", {"force": True, "strict": True}), "analysis"]
    assert analysis.datas == [("keep",)]
    assert (tmp_path / "dist/example.exe.config").read_text() == "config"


def test_matplotlib_hook_uses_app_cache_and_respects_override(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "executable", "/app/example")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)
    hook = Path(freezing.__file__).parent / "hooks/rthook_mplconfig.py"
    runpy.run_path(str(hook))
    assert os.environ["MPLCONFIGDIR"] == str(tmp_path / "example/matplotlib")
    assert (tmp_path / "example/matplotlib").is_dir()
    monkeypatch.setenv("MPLCONFIGDIR", "user-config")
    runpy.run_path(str(hook))
    assert os.environ["MPLCONFIGDIR"] == "user-config"
