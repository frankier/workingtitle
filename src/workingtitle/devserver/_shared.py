"""Lazy references and socket helpers shared with desktop hosting."""

from typing import Any
import importlib
import socket


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
