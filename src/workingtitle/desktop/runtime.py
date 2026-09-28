"""CLI and desktop lifecycle for ASGI desktop applications.

Application factories and preparation callbacks stay in the application.
Uvicorn and pywebview are imported only when their functionality is used.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import importlib
import importlib.util
import os
from pathlib import Path
import socket
import sys
import threading
import time
from typing import Any, Callable, Mapping
import webbrowser


@dataclass(frozen=True)
class WindowSpec:
    width: int = 1400
    height: int = 900


@dataclass(frozen=True)
class ReloadSpec:
    directories: tuple[Path, ...] = ()
    includes: tuple[str, ...] = ("*.py",)
    excludes: tuple[str, ...] = (
        "node_modules",
        ".venv",
        "build",
        "dist",
        ".desktop-build",
    )


@dataclass(frozen=True)
class AppSpec:
    name: str
    title: str
    factory: str
    description: str = ""
    window: WindowSpec = field(default_factory=WindowSpec)
    native_platforms: tuple[str, ...] = ("win32", "darwin")
    debug_env_var: str | None = None
    reload: ReloadSpec = field(default_factory=ReloadSpec)


def import_object(reference: str) -> Any:
    """Resolve a ``module:attribute`` reference without importing it earlier."""
    module, separator, attribute = reference.partition(":")
    if not separator or not module or not attribute:
        raise ValueError(f"expected module:attribute, got {reference!r}")
    value = importlib.import_module(module)
    for part in attribute.split("."):
        value = getattr(value, part)
    return value


def bind_socket(host="127.0.0.1", port=0):
    """Bind before reporting the URL, including when choosing a free port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(128)
        sock.set_inheritable(True)
    except BaseException:
        sock.close()
        raise
    return sock


def socket_url(sock):
    host, port = sock.getsockname()[:2]
    # A wildcard bind address is not a browser destination.
    if host == "0.0.0.0":
        host = "127.0.0.1"
    return f"http://{host}:{port}/"


class ServerThread:
    """Own an ASGI server and its socket; also usable as a context manager."""

    def __init__(self, app, sock, log_level="warning"):
        import uvicorn

        self.sock = sock
        self.server = uvicorn.Server(
            uvicorn.Config(app, log_level=log_level, ws="websockets")
        )
        self.thread = threading.Thread(
            target=self.server.run,
            kwargs={"sockets": [sock]},
            daemon=True,
            name="uvicorn",
        )

    @property
    def url(self):
        return socket_url(self.sock)

    def start(self, timeout=60.0):
        self.thread.start()
        deadline = time.monotonic() + timeout
        try:
            while not self.server.started:
                if not self.thread.is_alive():
                    raise RuntimeError("Server thread died during startup")
                if time.monotonic() > deadline:
                    raise TimeoutError("Server did not start in time")
                time.sleep(0.05)
        except BaseException:
            self.stop()
            raise
        return self

    def stop(self, timeout=10.0):
        self.server.should_exit = True
        if self.thread.ident is not None:
            self.thread.join(timeout)
            if self.thread.is_alive():
                self.server.force_exit = True
                self.thread.join(5.0)
        self.sock.close()
        if self.thread.is_alive():
            raise RuntimeError("Server thread did not stop")

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


class DesktopSession:
    """Per-launch native window access, suitable for application state.

    The session owns the one native window for a launch. Applications receive
    it through their own state or a closure and use either ``window`` directly
    or the dialog convenience methods. The dialog methods block until the user
    dismisses the dialog; call them from a worker thread, for example with
    ``starlette.concurrency.run_in_threadpool``.
    """

    def __init__(self, spec: AppSpec):
        self.spec = spec
        self.window = None

    def native_window_supported(self):
        """Whether this platform has a configured native-window backend."""
        return sys.platform in self.spec.native_platforms

    @property
    def native(self):
        """Whether a native window is open, and can therefore show dialogs."""
        return self.window is not None

    def _dialog(
        self,
        kind,
        *,
        directory=None,
        allow_multiple=False,
        save_filename="",
        file_types=(),
    ):
        """Show a pywebview file dialog and return its paths as ``Path``s.

        ``kind`` names a ``webview.FileDialog`` member. pywebview is imported
        here so a session without a window does not need the GUI installed.
        """
        if self.window is None:
            raise RuntimeError("no native window is available for dialogs")
        import webview

        chosen = self.window.create_file_dialog(
            getattr(webview.FileDialog, kind),
            directory=str(directory) if directory is not None else "",
            allow_multiple=allow_multiple,
            save_filename=save_filename,
            file_types=tuple(file_types),
        )
        return tuple(Path(path) for path in chosen or ())

    def open_folder(self, *, directory=None, allow_multiple=False):
        """Choose directories; return the selection, empty when cancelled."""
        return self._dialog(
            "FOLDER", directory=directory, allow_multiple=allow_multiple
        )

    def open_file(self, *, directory=None, allow_multiple=False, file_types=()):
        """Choose files; return the selection, empty when cancelled."""
        return self._dialog(
            "OPEN",
            directory=directory,
            allow_multiple=allow_multiple,
            file_types=file_types,
        )

    def save_file(self, *, directory=None, filename="", file_types=()):
        """Choose a destination; return it, or ``None`` when cancelled."""
        chosen = self._dialog(
            "SAVE",
            directory=directory,
            save_filename=filename,
            file_types=file_types,
        )
        return chosen[0] if chosen else None

    def run_window(self, app, sock, log_level="warning"):
        import webview

        with ServerThread(app, sock, log_level=log_level) as server:
            try:
                self.window = webview.create_window(
                    self.spec.title,
                    server.url,
                    width=self.spec.window.width,
                    height=self.spec.window.height,
                )
                # pywebview owns the main thread, including on macOS.
                webview.start()
            finally:
                self.window = None

    def run_browser(self, app, sock, open_browser=True, log_level="info"):
        with ServerThread(app, sock, log_level=log_level) as server:
            print(
                f"{self.spec.title} running at {server.url}  (Ctrl-C to quit)",
                flush=True,
            )
            if open_browser:
                webbrowser.open(server.url)
            try:
                while server.thread.is_alive():
                    server.thread.join(1.0)
            except KeyboardInterrupt:
                pass

    def run(self, app, host="127.0.0.1", port=0, *, mode="auto", open_browser=True):
        if mode not in {"auto", "native", "browser", "server"}:
            raise ValueError(f"unknown launch mode: {mode}")
        sock = bind_socket(host, port)
        try:
            if mode in {"browser", "server"} or (
                mode == "auto" and not self.native_window_supported()
            ):
                self.run_browser(
                    app, sock, open_browser=open_browser and mode != "server"
                )
                return
            try:
                self.run_window(app, sock)
            except Exception as exc:
                if mode == "native":
                    raise
                print(
                    f"Could not open a native window ({exc}); "
                    "falling back to the browser.",
                    file=sys.stderr,
                )
                sock.close()
                sock = bind_socket(host, port)
                self.run_browser(app, sock, open_browser=open_browser)
        finally:
            sock.close()

    def run_reload(self, host, port, *, open_browser=True, assets=None):
        import uvicorn
        from uvicorn.supervisors import ChangeReload

        class BuildOnReload(ChangeReload):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if assets is not None:
                    self.watch_filter = assets.watch_filter(self.watch_filter)

            def restart(self):
                if assets is not None:
                    try:
                        assets.ensure_built()
                    except Exception as exc:
                        # Keep serving the previous app while the user fixes
                        # the sources; a later edit retries the build.
                        print(f"Asset rebuild failed: {exc}", file=sys.stderr)
                        return
                super().restart()

        options = self.spec.reload
        with bind_socket(host, port) as sock:
            config = uvicorn.Config(
                self.spec.factory,
                factory=True,
                reload=True,
                reload_dirs=[str(p) for p in options.directories]
                + ([str(assets.root)] if assets is not None else []),
                reload_includes=list(options.includes),
                reload_excludes=list(options.excludes),
                ws="websockets",
                log_level="info",
            )
            server = uvicorn.Server(config)
            url = socket_url(sock)
            print(
                f"{self.spec.title} running at {url}  (reload enabled, Ctrl-C to quit)",
                flush=True,
            )
            if open_browser:
                webbrowser.open(url)
            try:
                BuildOnReload(config, target=server.run, sockets=[sock]).run()
            except KeyboardInterrupt:
                pass


def build_parser(spec: AppSpec, *, add_arguments=None, smoke_test=False):
    parser = argparse.ArgumentParser(prog=spec.name, description=spec.description)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 picks a free port")
    parser.add_argument(
        "--mode", choices=("auto", "native", "browser", "server"), default="auto"
    )
    parser.add_argument("--reload", action="store_true", help="Reload in browser mode")
    parser.add_argument("--debug", action="store_true", help="Enable debug and reload")
    if smoke_test:
        parser.add_argument("--smoke-test", action="store_true")
    else:
        parser.set_defaults(smoke_test=False)
    if add_arguments is not None:
        add_arguments(parser)
    return parser


def run_cli(
    spec: AppSpec,
    argv=None,
    *,
    add_arguments: Callable | None = None,
    prepare: Callable[[argparse.Namespace], Mapping[str, str] | None] | None = None,
    assets=None,
    smoke_test: Callable[[argparse.Namespace, DesktopSession], int] | None = None,
    session: DesktopSession | None = None,
) -> int:
    """Launch an app whose zero-argument factory reads the prepared environment.

    ``prepare(args)`` validates app options and returns environment overrides;
    ValueError is presented as an argparse error. Overrides are restored on exit.
    Smoke callbacks own their fixtures, app creation, and server lifecycle and
    bypass normal preparation. Pass a session to share window access with the app.
    """
    parser = build_parser(spec, add_arguments=add_arguments, smoke_test=smoke_test)
    args = parser.parse_args(argv)
    session = session or DesktopSession(spec)
    reload = (args.reload or args.debug) and not args.smoke_test
    if reload and (
        getattr(sys, "frozen", False) or importlib.util.find_spec("watchfiles") is None
    ):
        parser.error("reload requires watchfiles and an unfrozen process")
    if reload and args.mode == "native":
        parser.error("reload cannot run in native mode")

    environment = {}
    if not args.smoke_test and prepare is not None:
        try:
            environment.update(prepare(args) or {})
        except ValueError as exc:
            parser.error(str(exc))
    if spec.debug_env_var is not None and args.debug:
        environment[spec.debug_env_var] = "1"
    previous = {key: os.environ.get(key) for key in environment}
    try:
        os.environ.update(environment)
        if assets is not None:
            assets.ensure_built()
        if args.smoke_test:
            return smoke_test(args, session)
        if reload:
            session.run_reload(
                args.host,
                args.port,
                open_browser=args.mode != "server",
                assets=assets,
            )
        else:
            session.run(
                import_object(spec.factory)(),
                args.host,
                args.port,
                mode=args.mode,
            )
        return 0
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
