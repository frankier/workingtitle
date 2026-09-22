"""Coercers and annotated types for query-parameter models.

Query values always arrive as strings. These types encode the coercion
policies that recur across Starlette apps: lenient fallbacks for UI state,
strict positive integers for pagination, union shapes like "all" or an
integer, JSON-encoded lists, and safe file names.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator

from .errors import ParamError


def lenient_int(value: Any) -> int | None:
    """Coerce to int, mapping anything unparseable to None (the UI fallback)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


LenientInt = Annotated[int | None, BeforeValidator(lenient_int)]


def _positive_int(value: Any) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ParamError("must be a positive integer") from None
    if result < 1:
        raise ParamError("must be a positive integer")
    return result


PositiveInt = Annotated[int, BeforeValidator(_positive_int)]


def _optional_positive_int(value: Any) -> int | None:
    return None if value is None else _positive_int(value)


OptionalPositiveInt = Annotated[int | None, BeforeValidator(_optional_positive_int)]


def int_or(*literals: str):
    """Integers that also accept the given sentinel strings, e.g. ``int_or("all")``."""
    allowed = set(literals)
    choices = " or ".join(repr(literal) for literal in literals)

    def coerce(value: Any):
        if isinstance(value, str) and value in allowed:
            return value
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ParamError(f"must be an integer or {choices}") from None

    return Annotated[Literal[tuple(literals)] | int, BeforeValidator(coerce)]


def json_list_of(item_type: type, *, message: str = "must be a JSON list"):
    """A JSON-encoded list of ``item_type`` values inside one query parameter."""

    def coerce(value: Any) -> list:
        try:
            parsed = json.loads(value) if isinstance(value, (str, bytes)) else value
        except ValueError:
            raise ParamError(message) from None
        if not isinstance(parsed, list) or not all(
            isinstance(item, item_type) for item in parsed
        ):
            raise ParamError(message)
        return parsed

    return Annotated[list[item_type], BeforeValidator(coerce)]


def _file_stem(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in (".", "..")
        or "/" in value
        or "\\" in value
        or Path(value).name != value
    ):
        raise ParamError("must be a plain file name")
    return value


FileStem = Annotated[str, BeforeValidator(_file_stem)]


SortDir = Literal["asc", "desc"]
Sorter = tuple[str, SortDir]


def _sorters(value: Any) -> list[tuple[str, str]]:
    """Convert collected ``sort[n][field/dir]`` items to (field, dir) tuples."""
    if not isinstance(value, list):
        raise ParamError("invalid sorter")
    result = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"field", "dir"}:
            raise ParamError("invalid sorter")
        direction = item["dir"]
        if direction not in ("asc", "desc"):
            raise ParamError("invalid sorter")
        result.append((item["field"], direction))
    return result


Sorters = Annotated[list[Sorter], BeforeValidator(_sorters)]
