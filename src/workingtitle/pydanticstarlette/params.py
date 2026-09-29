"""Turning Starlette query parameters into validated Pydantic models."""

from __future__ import annotations

import functools
import inspect
import re
from typing import Any, TypeVar

from pydantic import BaseModel
from starlette.exceptions import HTTPException

from .errors import ParamError, error_message

ModelT = TypeVar("ModelT", bound=BaseModel)

_INDEXED_RE = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)\[(\d+)\]\[([A-Za-z_][A-Za-z0-9_]*)\]$"
)


def collect_query_params(query: Any) -> dict[str, Any]:
    """Flatten query parameters into a dict for model validation.

    Scalar keys map to their (last) value. Indexed keys following the
    ``name[<index>][<part>]`` convention (Tabulator's remote sort, PHP-style
    form arrays) are grouped into a list of dicts ordered by index, so a
    model can pick them up with ``validation_alias="name"``. Malformed or
    repeated indexed keys are rejected rather than silently ignored.

    ``query`` may be a Starlette ``QueryParams`` or any mapping, so handlers
    can be unit-tested with plain dict fakes.
    """
    data: dict[str, Any] = {}
    indexed: dict[str, dict[int, dict[str, str]]] = {}
    items = query.multi_items() if hasattr(query, "multi_items") else query.items()
    for key, value in items:
        match = _INDEXED_RE.match(key)
        if match is None:
            if "[" in key:
                raise ParamError(f"invalid parameter: {key}")
            data[key] = value
            continue
        name, index, part = match.groups()
        item = indexed.setdefault(name, {}).setdefault(int(index), {})
        if part in item:
            raise ParamError(f"duplicate parameter: {key}")
        item[part] = value
    for name, items in indexed.items():
        data[name] = [items[index] for index in sorted(items)]
    return data


def parse_query(query: Any, model: type[ModelT]) -> ModelT:
    """Validate query parameters into an instance of ``model``.

    Raises Pydantic ``ValidationError`` or ``ParamError`` (both are
    ``ValueError`` subclasses) on bad input.
    """
    return model.model_validate(collect_query_params(query))


def query_params(model: type[BaseModel] | None = None):
    """Validate a handler's query parameters and map errors to 400.

    The decorated handler keeps its public ``(request)`` signature. When a
    model is given, it is validated from the query string and injected as a
    second argument: the handler becomes ``handler(request, params)``.

    Validation failures and ``ValueError`` raised anywhere in the handler
    become a Starlette 400 ``HTTPException`` naming the problem, so an app's
    exception handler can customize the response. Other Starlette
    ``HTTPException`` instances (e.g. 404 for missing resources) propagate
    untouched.
    """

    def decorate(handler):
        @functools.wraps(handler)
        async def endpoint(request):
            try:
                if model is None:
                    result = handler(request)
                else:
                    result = handler(request, parse_query(request.query_params, model))
                if inspect.iscoroutine(result):
                    result = await result
                return result
            except ValueError as exc:  # includes ValidationError and ParamError
                raise HTTPException(status_code=400, detail=error_message(exc)) from exc

        return endpoint

    return decorate


def require_found(value: Any, options: Any, label: str = "value"):
    """Raise 404 unless ``value`` is one of the known ``options``.

    For lookups where the query parameter names an existing resource (a
    processing step, a log file) rather than just carrying a well-formed
    value.
    """
    if value not in options:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return value
