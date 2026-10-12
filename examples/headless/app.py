"""Import-time StaticFiles validation demonstrates build-before-import."""

from pathlib import Path
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
assert (ROOT / "static/index.js").is_file()
assert (ROOT / "static/index.css").is_file()


async def index(request):
    return HTMLResponse(
        '<link rel="stylesheet" href="/static/index.css">'
        '<h1>Headless workingtitle</h1><script src="/static/index.js"></script>'
    )


app = Starlette(
    routes=[Route("/", index), Mount("/static", StaticFiles(directory=ROOT / "static"))]
)
