# Headless ASGI development and asset builds

Install `workingtitle[devserver]` for Uvicorn, watchfiles and WebSocket support.
A runnable npm-backed example is in `examples/headless` in the repository.
It does not install pywebview, PyInstaller or Bokeh. Imports of the server and
application-owned compilers stay lazy. Asset builds alone need no extra.

## An application-owned CLI

Keep the plan in a module **outside any package whose `__init__.py` eagerly
imports the app**. For example, a checkout-root `web_assets.py`:

```python
from pathlib import Path
from workingtitle.devserver import AssetPlan, NpmBuild

PROJECT_ROOT = Path(__file__).resolve().parent
ASSETS = AssetPlan(
    root=PROJECT_ROOT,
    cache_dir=".workingtitle-build",
    steps=(NpmBuild(
        name="frontend",
        inputs=("src/js/**", "src/css/**", "src/vms/**/*.html", "src/vms/**/*.py"),
        outputs=("src/vms/static/index.js", "src/vms/static/index.css"),
        script="build",
    ),),
    excludes=("node_modules", ".venv", "__pycache__", ".git", "build", "dist",
              ".venv-local", "results", "ray_artifacts"),
)
```

`npm run build` should produce both outputs (for example, Tailwind 4 and esbuild).
The npm manifest and lockfile are tracked automatically relative to `NpmBuild.cwd`.
Use `cwd`, `script` and `install_args` to customize the commands. Dependencies
are installed only when their manifest/lock fingerprint changes or the installed
`node_modules/.package-lock.json` marker is missing. Source edits only rebuild.

Tailwind scans `../vms` in this example. Track templates and Python files that
contain utility classes, and extend these globs when introducing other scanned
file types. Generated outputs are excluded from filesystem reload events.

In a separate application CLI module (guarding entry for spawned processes):

```python
from web_assets import ASSETS
from workingtitle.devserver import ReloadSpec, run_server

if __name__ == "__main__":
    run_server(
        "vms:app",
        assets=ASSETS,
        host="127.0.0.1",
        port=8000,
        reload=ReloadSpec(
            directories=(ASSETS.root / "src",),
            excludes=ReloadSpec().excludes + (".venv-local", "results", "ray_artifacts"),
        ),
        log_level="info",
    )
```

Use `factory=True` with an import string such as `vms:create_app` for a factory.
Omit `reload` for normal serving, including browser tests. Uvicorn configuration
such as `lifespan`, `root_path`, SSL options and `workers` is forwarded. Reload
and multiple workers cannot be combined. Builds happen in the supervisor before
app import/initialization, never independently in workers or reload children.
No browser opens. Ordinary `uvicorn --reload` does **not** use this supervisor.

Reload accepts non-Python asset inputs, including additions, deletions and
renames. Content and relative paths contribute to fingerprints; missing outputs
force rebuilding. Cache, dependencies, virtualenvs and outputs do not trigger
reload. Add database, results, alternate virtualenv and Ray directories to
both exclusions as appropriate. `ReloadSpec.excludes` supports Uvicorn's glob
rules and additionally ignores matching directory components even when absent
at startup. `AssetPlan.excludes` contains directory component names.

A failed initial build prevents startup. Failed reload builds report the error
and retain the current child; a later source edit retries. Actions raising
`BuildUnavailable` explicitly warn and permit existing outputs in development,
without recording success; strict builds reject fallback. Ordinary errors
always propagate. A forced failure also invalidates an earlier success stamp.

Builds of a plan are guarded with an exclusive `build.lock` in the cache.
Concurrent callers fail clearly instead of racing. All callers building the
same output tree must use the same cache directory; do not configure separate
plans/caches to write overlapping outputs. After a killed build, confirm it is
no longer running before removing the stale lock file.

## Strict builds and deployment

Build independently of the app, without initializing Ray or Bokeh server state:

```sh
python -m workingtitle.devserver web_assets:ASSETS
# Optional unconditional rebuild:
python -m workingtitle.devserver web_assets:ASSETS --force
```

Equivalent application code is `ASSETS.ensure_built(strict=True)`. This is also
the integration point for CI, Docker, tests and wheel/sdist preparation.

For apitofsim-web's later asset-untracking migration:

1. Build a clean checkout before serving or browser tests, even when tests
   launch ordinary Uvicorn without reload.
2. Run a strict build before constructing wheels/container images. Explicitly
   include generated assets in wheels and deployment images. If consumers
   rebuild from an sdist, include frontend inputs, templates, compiler config,
   package.json and the npm lockfile there. `uv_build` does not automatically
   execute the asset plan.
3. In installed applications, construct a plan rooted at the package's resource
   directory with `source=False`. It validates outputs and fails clearly when
   missing, without compiler imports, npm, cache writes or a checkout. It does
   not write to site-packages. Frozen apps use the same validation policy.
4. Ignore only generated JS/CSS and build state, preserving hand-authored static
   files. Replace the npm watcher pane in `run_servers.sh` with the CLI above
   and update development instructions. Removing apitofsim-web's tracked
   assets is a separate change.

The shared default cache is `.workingtitle-build`, including through desktop
compatibility exports. Existing `.desktop-build` stamps are not migrated;
changing the default causes one rebuild. Pass `cache_dir=".desktop-build"` to
retain old stamps. Both default directory names are excluded by `ReloadSpec`.
Desktop startup, reload and strict PyInstaller builds use this shared layer;
window/lifecycle/packaging APIs remain in `workingtitle.desktop`.

## Lazy compiler adapters and ordered steps

`PythonBuild` is compiler-neutral. A Bokeh adapter is application-owned and
should import the selected compiler inside its action, accept `BuildContext`,
run that version's supported compiler API and validate its bundle/metadata.
Workingtitle does not require Bokeh or prescribe a compiler invocation.

For example, in `web_assets.py`, without importing the web app:

```python
from importlib.metadata import version
from workingtitle.devserver import PythonBuild

MODEL_BUILD = PythonBuild(
    name="models",
    inputs=("models/**/*.ts", "models/**/*.js", "models/**/*.css",
            "models/**/*.py", "compiler-config.json"),
    outputs=("generated/models.js", "generated/models.json"),
    action="model_compiler:build",
    cache_key=f"bokeh={version('bokeh')};adapter=1",
)
```

An application-owned `model_compiler.py` can follow this structure:

```python
from workingtitle.devserver import BuildContext, BuildUnavailable


def build(context: BuildContext):
    try:
        from my_compiler_adapter import compile_and_validate
    except ImportError as exc:
        raise BuildUnavailable("model compiler unavailable") from exc
    compile_and_validate(context.root, strict=context.strict)
```

`my_compiler_adapter` owns the version-specific Bokeh API, output serialization,
and bundle validation. Raise ordinary errors for compilation failures; use
`BuildUnavailable` only for intentional development fallback. Metadata lookup
in the plan is not a compiler import; environments supporting unavailable
compilers can handle `PackageNotFoundError` and supply an explicit cache key.
Update the key when changing compiler/adapter configuration. Alternatively,
track a version manifest as an input and regenerate it from the selected
compiler version before checking the plan. Environment-only upgrades must
change this key or manifest; source fingerprints alone cannot detect them.

Declare multiple steps in order. A downstream step can declare
`inputs=("generated/models.js", "generated/models.json")`; these earlier outputs
are fingerprinted even though filesystem reload ignores generated assets.
Their changed contents invalidate downstream work. A step's own outputs stay
excluded from its fingerprints so broad globs cannot create rebuild loops.
