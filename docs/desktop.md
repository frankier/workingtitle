# Desktop helpers

`workingtitle.desktop` contains shared code for launching and packaging ASGI
desktop applications. The runtime accepts an ASGI application; it does not
require Starlette-specific routing.

Install `workingtitle[desktop]` for Uvicorn, WebSockets, and pywebview on Windows
and macOS. `workingtitle[desktop-dev]` adds watchfiles;
`workingtitle[desktop-build]` adds PyInstaller and its contributed hooks. Use
both extras when developing and packaging. Importing `workingtitle.desktop`
does not load these optional dependencies.

## Application and CLI

Put lightweight identity and window settings in an application-owned module:

```python
# example/desktop_app.py
from workingtitle.desktop import AppSpec, DesktopSession, WindowSpec

APP = AppSpec(
    name="example",
    title="Example Viewer",
    description="View local results.",
    factory="example.asgi:create_app_from_env",
    debug_env_var="EXAMPLE_DEBUG",
    window=WindowSpec(width=1400, height=900),
)
SESSION = DesktopSession(APP)
```

The factory is a zero-argument function. It should read application settings
and the debug flag from the environment, then construct the ASGI app. Avoid
creating another app at module import time. This same factory runs in the
normal process and in the reload subprocess.

```python
# example/cli.py
from workingtitle.desktop import run_cli
from .desktop_app import APP, SESSION


def add_arguments(parser):
    parser.add_argument("--config")


def prepare(args):
    # Validate here; ValueError becomes a normal argparse error.
    return {"EXAMPLE_CONFIG": args.config} if args.config else {}


def main(argv=None):
    return run_cli(
        APP, argv,
        add_arguments=add_arguments,
        prepare=prepare,
        session=SESSION,
    )
```

`prepare` returns string environment overrides. They are in place before
asset building or app creation, inherited by reload children, and restored
when the runner exits. Existing environment settings are otherwise preserved.

The executable bootstrap should run multiprocessing setup before importing
the application's CLI:

```python
# example/__main__.py
if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()
    from .cli import main

    raise SystemExit(main())
```

For a PyInstaller script entrypoint, use the absolute import
`from example.cli import main` rather than the relative import above.
Keep the existing project console script pointing at `example.cli:main`.

Common CLI options:

| Option | Behavior |
| --- | --- |
| `--host`, `--port` | Default to loopback and a dynamically selected port |
| `--mode auto` | Native window on Windows/macOS, browser elsewhere; browser fallback on native failure |
| `--mode native` | Require a native window; propagate failures |
| `--mode browser` | Serve and open the system browser |
| `--mode server` | Serve without opening a window or browser |
| `--no-window` | Select browser mode, overriding `--mode` |
| `--no-browser` | Suppress system-browser opening, including fallback; native windows remain enabled |
| `--reload` | Reload in browser/server mode; requires watchfiles and an unfrozen process |
| `--debug` | Enable the configured debug environment flag and imply reload |
| `--smoke-test` | Available only when a smoke callback is supplied |

`--reload --mode native` is rejected. `--debug` suppresses reloading during a
smoke test. A smoke callback has signature `smoke_test(args, session) -> int`;
it bypasses normal `prepare` and factory creation, so it can own temporary
fixtures and configuration. It runs after asset validation/building.

Applications can attach `SESSION` to their app state. `session.native` is true
while a native window is open, and `session.window` is the underlying pywebview
window or `None` in browser and server mode. The session also provides blocking
dialog helpers that return `Path` objects:

| Method | Returns |
| --- | --- |
| `open_folder(*, directory=None, allow_multiple=False)` | `tuple[Path, ...]`, empty when cancelled |
| `open_file(*, directory=None, allow_multiple=False, file_types=())` | `tuple[Path, ...]`, empty when cancelled |
| `save_file(*, directory=None, filename="", file_types=())` | `Path`, or `None` when cancelled |

`file_types` uses pywebview's `"Description (*.ext1;*.ext2)"` format. The
helpers raise `RuntimeError` when no window is open, so check `session.native`
first. They block until the user dismisses the dialog; call them from a worker
thread:

```python
from starlette.concurrency import run_in_threadpool

if session.native:
    chosen = await run_in_threadpool(session.open_folder, allow_multiple=True)
```

Applications that need behavior beyond these helpers can still use
`session.window` directly. Application-specific dialog behavior stays in the
app. The GUI loop must run on the main thread.

`ServerThread(app, bind_socket(...))` is also a context manager for custom
smoke checks. It owns startup readiness, shutdown, and socket cleanup.

## Frontend assets

Declare an ordered build plan in an application-owned build module:

```python
from pathlib import Path
from workingtitle.desktop import AssetPlan, NpmBuild, PythonBuild

ASSETS = AssetPlan(
    root=Path(__file__).resolve().parents[2],  # explicit source checkout root
    steps=(
        NpmBuild(
            name="frontend",
            inputs=("src/js/**", "src/css/**", "src/example/templates/**"),
            outputs=(
                "src/example/static/generated/index.js",
                "src/example/static/generated/index.css",
            ),
        ),
        # Optional compiler adapter owned by the application:
        PythonBuild(
            name="extension",
            action="example.extension_build:build",
            inputs=("src/extension/**/*.ts", "src/extension/package.json"),
            outputs=("src/extension/dist/extension.json",),
        ),
    ),
)
```

Pass `assets=ASSETS` to `run_cli` to build before startup and each reload.
Call `ASSETS.ensure_built()` for an explicit build, or
`ASSETS.ensure_built(force=True)` to run every step. No separate npm watcher is
needed when using reload. Node/npm must already be installed. Development
builds are tolerant by default; `ensure_built(strict=True)` makes a fallback an
error, and packaging always uses strict mode.

Paths and globs are root-relative. Inputs should include all compiler configs,
templates, and sources affecting the output. npm steps automatically include
`package.json` and `package-lock.json`, run `npm ci --ignore-scripts` when the
dependency stamp changes, and invoke `npm run build` (configurable via `script`).
`cwd` supports nested npm projects. On Windows the runner uses `npm.cmd`.
Override `install_args` if a project's dependencies require install scripts.

Build fingerprints include filenames and contents, so source deletion and
renaming also cause a rebuild. Missing output files cause a rebuild. Fingerprint
state lives under `.desktop-build/`; add that directory to the application's
ignore file. Do not run concurrent builds against the same output tree.

Python actions are lazy `module:attribute` references to callables. An action
may take no arguments or a single `BuildContext`, which exposes `name`, `root`,
`force`, and `strict`. It must produce the declared outputs, raise on failure,
or raise `BuildUnavailable` to fall back to stale assets. A fallback never
writes a fingerprint stamp, so the next call retries; `strict=True` (used by
packaging) turns that fallback into an error. An adapter around an
application's current extension builder can therefore attempt compilation in
development, signal `BuildUnavailable` when only the stale bundle exists, and
fail the package build under `strict=True`. The extension compiler and its
bundle-integrity checks remain application-owned.

Reload watches declared input globs, including nested sources, CSS, templates,
and npm manifests. Generated outputs, build state, `node_modules`, virtualenvs,
`build`, and `dist` are excluded. AppSpec's `ReloadSpec` can also configure
Python watch directories and patterns. A failed rebuild leaves the previous
server running and retries after the next source edit; initial build failures
propagate.

For installed wheels, use a resource-root plan with `source=False` and output
paths relative to that root. Frozen execution also unconditionally switches to
output validation. Neither mode invokes Node or imports a compiler, even with
`force=True`. Keep source-only build declarations out of frozen startup imports
when their paths differ from the bundle layout.

## PyInstaller

Keep a small application-owned `.spec` file. Put its recipe in a lightweight
module that can be imported from the build environment:

```python
from pathlib import Path
from workingtitle.desktop.freezing import BundleSpec, PackageData, build_bundle
from example.desktop_app import APP
from example.build import ASSETS

recipe = BundleSpec(
    app=APP,
    root=Path(SPECPATH),  # injected by PyInstaller
    entrypoint="src/example/__main__.py",
    packages=(PackageData("example"),),
    matplotlib=True,
    bundle_identifier="org.example.viewer",
    version="0.1.0",
)
bundle = build_bundle(recipe, globals(), assets=ASSETS)
```

Install the application in the build environment first. `build_bundle` builds
assets before analysis, produces an onedir executable, and wraps it in a
macOS `.app` when appropriate. It uses the PyInstaller constructors supplied
by the `.spec` namespace. Asset steps run with `force=True, strict=True`, so a
stale-asset fallback aborts the package build. `analysis_options(recipe)` is
available when an app needs to retain its own construction sequence.

Recipes support package-data include/exclude patterns, distribution metadata,
submodule collection with excluded prefixes, explicit hidden imports, raw data
and binaries, hook paths, runtime hooks, and post-analysis `data_filter`.
`adjacent_files={"win32": ("ci/windows/example.exe.config",)}` copies files
beside the collected executable rather than into `_internal`.

The app factory's module and Uvicorn's dynamically selected implementations
are collected automatically. GUI backend collection follows AppSpec's native
platform policy; supported native recipes are Windows and macOS. Domain-library
recipes (MNE, Panel/Holoviews, mplbed, Bokeh extensions) stay in the consuming
application. No broad scientific-library exclusions are applied implicitly.

`matplotlib=True` collects Matplotlib data/metadata and installs an early
runtime hook that sets a writable cache under the executable's name. Existing
`MPLCONFIGDIR` overrides are respected. Application runtime hooks run after
this hook.

## Validation

Run `uv sync --locked --group test` and `uv run --locked python -m pytest`.
Tests cover real loopback server startup/shutdown, native fallback cleanup,
CLI preparation/reload ordering, incremental builds, npm lock changes, asset
watch filtering, and packaging construction. Full application builds and
native Windows/macOS GUI tests belong to the later integration stage.
