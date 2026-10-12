"""Headless ASGI startup and build-before-restart supervision."""

from dataclasses import dataclass
from pathlib import Path
import importlib.util
import sys

from ._shared import bind_socket, socket_url


@dataclass(frozen=True)
class ReloadSpec:
    directories: tuple[Path, ...] = ()
    includes: tuple[str, ...] = ("*.py",)
    excludes: tuple[str, ...] = (
        "node_modules",
        ".venv",
        "__pycache__",
        ".git",
        "build",
        "dist",
        ".workingtitle-build",
        ".desktop-build",
    )


def run_server(
    app: str,
    *,
    factory=False,
    assets=None,
    host="127.0.0.1",
    port=8000,
    reload: ReloadSpec | None = None,
    on_ready=None,
    **uvicorn_options,
):
    """Build before Uvicorn imports an app object or constructs a factory.

    Pass a ReloadSpec to enable the build supervisor. Uvicorn options such as
    lifespan, root_path, SSL settings and log_level are forwarded to Config.
    Builds run once in the supervisor, including with multiple workers.
    ``on_ready(url)`` is an optional socket-bound callback used by desktop.
    """
    if not isinstance(app, str):
        raise TypeError("app must be an ASGI module:attribute import string")
    reserved = {
        "app",
        "factory",
        "host",
        "port",
        "reload",
        "reload_dirs",
        "reload_includes",
        "reload_excludes",
    }
    if reserved.intersection(uvicorn_options):
        raise ValueError("configure reload through ReloadSpec")
    if reload is not None and (
        getattr(sys, "frozen", False) or importlib.util.find_spec("watchfiles") is None
    ):
        raise RuntimeError("reload requires watchfiles and an unfrozen process")
    if reload is not None and uvicorn_options.get("workers", 1) != 1:
        raise ValueError("reload cannot be combined with multiple workers")
    if assets is not None:
        assets.ensure_built()

    import uvicorn

    options = {"ws": "websockets", "log_level": "info", **uvicorn_options}
    if reload is not None:
        options.update(
            reload=True,
            reload_dirs=[str(p) for p in reload.directories]
            + ([str(assets.root)] if assets is not None else []),
            reload_includes=list(reload.includes),
            reload_excludes=list(reload.excludes),
        )
    config = uvicorn.Config(app, factory=factory, host=host, port=port, **options)
    server = uvicorn.Server(config)
    with bind_socket(host, port) as sock:
        if on_ready is not None:
            on_ready(socket_url(sock))
        try:
            if reload is not None:
                _build_supervisor(assets, reload)(
                    config, target=server.run, sockets=[sock]
                ).run()
            elif config.workers > 1:
                from uvicorn.supervisors import Multiprocess

                Multiprocess(config, target=server.run, sockets=[sock]).run()
            else:
                server.run(sockets=[sock])
        except KeyboardInterrupt:
            pass


def _build_supervisor(assets, options):
    # Imported here so importing workingtitle.devserver needs no server extra.
    from uvicorn.supervisors import ChangeReload

    class BuildOnReload(ChangeReload):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            base = self.watch_filter

            def excludes(path):
                return any(part in options.excludes for part in Path(path).parts)

            extended = assets.watch_filter(base) if assets is not None else base
            self.watch_filter = lambda path: not excludes(path) and extended(path)

        def restart(self):
            if assets is not None:
                try:
                    assets.ensure_built()
                except Exception as exc:
                    print(f"Asset rebuild failed: {exc}", file=sys.stderr)
                    return
            super().restart()

    return BuildOnReload
