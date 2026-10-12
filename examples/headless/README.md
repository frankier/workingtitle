# Headless example

Requires Python with `workingtitle[devserver]` installed and Node/npm.
From this directory, run `python serve.py`, then visit http://127.0.0.1:8000.
Neither generated static asset exists in a clean checkout; the supervisor runs
`npm run build` before importing `app`. Edit either frontend file to rebuild
and reload. No separate npm watcher is needed.

Build only: `python -m workingtitle.devserver web_assets:ASSETS`.
The minimal npm script copies CSS and JS without external dependencies; an
application can replace it with Tailwind/esbuild without changing the plan.
