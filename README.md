# workingtitle

Shared helpers for Python web applications:

- `workingtitle.pydanticstarlette`: query-parameter validation for plain
  Starlette applications, backed by Pydantic models.
- `workingtitle.devserver`: incremental asset builds and headless ASGI reload.
- `workingtitle.desktop`: ASGI desktop launching, frontend builds, and
  PyInstaller packaging.

## Installation

    $ uv add workingtitle

Headless serving uses `workingtitle[devserver]`; see [the guide](docs/devserver.md).
The desktop helpers live behind extras: `workingtitle[desktop]`.

## Documentation

The docs are published at <https://frankier.github.io/workingtitle/>, which
redirects to the newest version. Every release is built under its own version
and the sidebar links between them.

- [Pydantic Starlette guide](https://frankier.github.io/workingtitle/pydanticstarlette/)
- [Desktop guide](https://frankier.github.io/workingtitle/desktop/)
- [API reference](https://frankier.github.io/workingtitle/api/)

Build the docs for every version, or only for the working tree:

    $ uv run sphinx-polyversion docs/poly.py
    $ uv run sphinx-polyversion -l docs/poly.py

## Contributing

Set up a dev environment with [uv](https://docs.astral.sh/uv/):

    $ uv sync --all-groups --all-extras

Run the tests:

    $ uv run pytest

Lint and format:

    $ uv run ruff check ./src
    $ uv run ruff format ./src
