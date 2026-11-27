"""Embed a mounted Bokeh server document in a Starlette template."""

from bokeh.embed import server_document
from markupsafe import Markup


def bokeh_document(request, path, *args, mount="bokeh", **options):
    url = str(request.url_for(mount, path=path))
    return Markup(server_document(url, *args, **options))
