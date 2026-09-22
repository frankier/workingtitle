"""Error reporting for rejected query parameters."""

from __future__ import annotations

from pydantic import ValidationError
from starlette.responses import Response

_VALUE_ERROR_PREFIX = "Value error, "


class ParamError(ValueError):
    """Raised for invalid query parameters outside of model validation.

    A subclass of ``ValueError`` so that Pydantic recognises it inside
    validators and :func:`pydanticstarlette.query_params` recognises it
    anywhere inside a handler.
    """


def error_message(exc: Exception) -> str:
    """Plain-text message for a failure; the first validation error wins."""
    if isinstance(exc, ValidationError):
        first = exc.errors(include_url=False)[0]
        loc = ".".join(str(part) for part in first["loc"])
        msg = first["msg"]
        if msg.startswith(_VALUE_ERROR_PREFIX):
            msg = msg[len(_VALUE_ERROR_PREFIX) :]
        return f"{loc}: {msg}" if loc else msg
    return str(exc)


def error_response(exc: Exception, status_code: int = 400) -> Response:
    return Response(error_message(exc), status_code=status_code, media_type="text/plain")
