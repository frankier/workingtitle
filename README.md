# workingtitle

Shared helpers for Python web applications:

- `workingtitle.pydanticstarlette`: query-parameter validation for plain
  Starlette applications, backed by Pydantic models.
- `workingtitle.desktop`: ASGI desktop launching, frontend builds, and
  PyInstaller packaging.

## Installation

    $ uv add workingtitle

The desktop helpers live behind extras: `workingtitle[desktop]`,
`workingtitle[desktop-dev]`, and `workingtitle[desktop-build]`.

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
