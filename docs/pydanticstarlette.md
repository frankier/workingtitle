# Pydantic Starlette

Query-parameter validation for plain Starlette applications, backed by
Pydantic models. FastAPI-style validation without the framework — no
OpenAPI, no dependency injection, no routing changes.

## Usage

```python
from enum import Enum

from pydantic import BaseModel, Field
from workingtitle.pydanticstarlette import PositiveInt, Sorters, query_params


class ReportType(str, Enum):
    daily = "daily"
    weekly = "weekly"


class ReportParams(BaseModel):
    report: ReportType
    page: PositiveInt = 1
    sorters: Sorters = Field(default_factory=list, validation_alias="sort")


@query_params(ReportParams)
async def report_data(request, params):
    ...  # params is a validated ReportParams
```

Invalid input never reaches the handler: it raises a Starlette
`HTTPException` with status `400` and a detail naming the offending parameter.
`ValueError` raised inside the handler body (e.g. "Unknown sort field") also
becomes a 400; other Starlette `HTTPException` instances (e.g. 404 lookups)
propagate untouched. Without a custom exception handler, Starlette displays
the detail in its default plain-text response.

Register a Starlette exception handler to show a custom bad request page:

```python
from html import escape

from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route


async def bad_request(request, exc):
    return HTMLResponse(
        f"<h1>Bad request</h1><p>{escape(str(exc.detail))}</p>",
        status_code=400,
    )


app = Starlette(
    routes=[Route("/reports", report_data)],
    exception_handlers={400: bad_request},
)
```

`@query_params()` with no model wraps a handler purely for the error
mapping, without injecting anything.

## Building blocks

| Export | Purpose |
| --- | --- |
| `query_params(model=None)` | Handler decorator: validate + inject, raise 400 for errors |
| `parse_query(query, model)` | Same parsing outside a handler (e.g. in helpers) |
| `collect_query_params(query)` | Flattens scalars and `name[i][part]` indexed groups |
| `LenientInt` | `maybe_int` semantics: unparseable falls back to `None` |
| `PositiveInt` / `OptionalPositiveInt` | Strict `>= 1` integers for pagination etc. |
| `int_or("all")` | Integers that also accept sentinel strings |
| `json_list_of(str)` | A JSON-encoded list inside one query parameter |
| `FileStem` | Safe bare file name (no separators or `..`) |
| `Sorters` | Tabulator remote-sort `sort[n][field/dir]` tuples |
| `require_found(value, options, label)` | 404 unless the value is a known id |
| `ParamError` | `ValueError` subclass for parameter errors in app code |

Indexed keys (`sort[0][field]=id`) are grouped by `collect_query_params`
into `{"sort": [{"field": "id", ...}]}` (ordered by index), so a model
field picks them up via `validation_alias="sort"`. Malformed or repeated
indexed keys are rejected instead of silently ignored.

See the [API reference](api.md) for the full signatures and docstrings.
