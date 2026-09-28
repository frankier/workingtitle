"""Optional desktop hosting, frontend builds, and PyInstaller support.

Importing this package does not import a GUI, compiler, or ASGI server.
"""

from .assets import AssetPlan, BuildContext, BuildUnavailable, NpmBuild, PythonBuild
from .runtime import (
    AppSpec,
    DesktopSession,
    ReloadSpec,
    ServerThread,
    WindowSpec,
    bind_socket,
    build_parser,
    run_cli,
    socket_url,
)

__all__ = [
    "AppSpec",
    "AssetPlan",
    "BuildContext",
    "BuildUnavailable",
    "DesktopSession",
    "NpmBuild",
    "PythonBuild",
    "ReloadSpec",
    "ServerThread",
    "WindowSpec",
    "bind_socket",
    "build_parser",
    "run_cli",
    "socket_url",
]
