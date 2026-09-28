# workingtitle

[`workingtitle`](https://github.com/frankier/workingtitle/) is a collection of
small shared helpers for Python web applications:

- [`workingtitle.pydanticstarlette`](pydanticstarlette.md) — query-parameter
  validation for plain Starlette applications, backed by Pydantic models.
- [`workingtitle.desktop`](desktop.md) — ASGI desktop launching, frontend
  builds, and PyInstaller packaging.

## Installation

    $ uv add workingtitle

Install the optional desktop helpers with:

    $ uv add "workingtitle[desktop]"

```{toctree}
:maxdepth: 2
:hidden:

pydanticstarlette
desktop
api
```
