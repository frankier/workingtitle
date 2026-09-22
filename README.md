# pydanticstarlette

Robot text below.

Query-parameter validation for plain Starlette applications, backed by
Pydantic models. FastAPI style validation without the framework — no
OpenAPI, no dependency injection, no routing changes. 

## Usage

```python
from pydantic import BaseModel
from pydanticstarlette import PositiveInt, Sorters, query_params


class ReportParams(BaseModel):
    report: ReportType
    page: PositiveInt = 1
    sorters: Sorters = Field(default_factory=list, validation_alias="sort")


@query_params(ReportParams)
async def report_data(request, params):
    ...  # params is a validated ReportParams
```

Invalid input never reaches the handler: it becomes a `400` plain-text
response naming the offending parameter. `ValueError` raised inside the
handler body (e.g. "Unknown sort field") also becomes a 400; Starlette
`HTTPException` (e.g. 404 lookups) propagates untouched.

`@query_params()` with no model wraps a handler purely for the error
mapping, without injecting anything.

## Building blocks

| Export | Purpose |
| --- | --- |
| `query_params(model=None)` | Handler decorator: validate + inject, map errors to 400 |
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
