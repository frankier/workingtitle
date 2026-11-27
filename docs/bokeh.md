# Bokeh plot workspaces

Install `workingtitle[bokeh]` on Python 3.12 or newer for Bokeh 3.10.x.

```python
from bokeh.layouts import row, column
from bokeh.models import Slider
from bokeh.plotting import figure

from workingtitle.bokeh.widgets import HelpIcon, control_group
from workingtitle.bokeh.workspace import FrameFullscreen, Sidebar

settings = control_group("Display", row(Slider(start=1, end=10, value=5),
                                         HelpIcon("Choose the line width")))
sidebar = Sidebar.create(settings, widths=(200, 40), button_widths=(110, 30),
                         labels=("Hide controls", "»"))
plot = figure(sizing_mode="stretch_both")
frame = column(row(sidebar.shell, plot, sizing_mode="stretch_both"),
               sizing_mode="stretch_both")
fullscreen = FrameFullscreen(frame)
sidebar.remember_in_browser(fullscreen)
plot.add_tools(fullscreen.action())
```

Add `frame` to the document. The sidebar remembers its open state independently
in each mode. Pass Bokeh dialogs to `FrameFullscreen(frame, dialogs=[...])` to
keep them accessible on entry and exit. A rebuilt plot can use a fresh
`fullscreen.action()` against the same frame. Use `fullscreen.button()` for a
layout control and `prepare_toolbar(plot)` for single-figure fullscreen.

Server-driven layouts can observe `fullscreen.state.text` and
`sidebar.toggle.active`, use a separate `PanelMode` per display mode, and
apply the resulting state with `sidebar.show()`. The two-panel
`apply_layout` helper accepts the mounted frame, body, workspace, center,
left/right columns, content columns and toggles as attributes of one object.
It supports viewport, contained and page sizing, plus a bottom details panel.

For browser alignment callbacks, prefix the callback code with
`workingtitle.bokeh.browser.ON_PLOT_FRAME` and call
`onPlotFrame(owner, key, findPlot, (view, bbox) => { ... })`. Repeated
notifications sharing the owner and key run once on the next animation frame.
The plot lookup runs after layout and only positive frame dimensions reach
the callback.

`workingtitle.bokeh.embed.bokeh_document(request, path, **options)` resolves
a Starlette mount (named `bokeh` by default) and forwards the options to
Bokeh's server document embedder.

## Help widget distribution

Bokeh resolves extension assets against a top-level Python package. The public
`workingtitle.bokeh.widgets.HelpIcon` lives in the `workingtitle_bokeh`
extension and the wheel includes its compiled browser code. Frozen builds
should collect the extension's `bokeh.ext.json`, `package.json` and `dist/*.js`.
After changing the TypeScript, build with Bokeh 3.10.2 and Node.js using
`bokeh build src/workingtitle_bokeh` and commit the rebuilt JavaScript.

When CSS flex sizing changes a panel's width independently of the outer frame,
register `observe_panel_width(doc, panel)` during document construction. It
recomputes Bokeh's geometry once the panel has a positive new width,
keeping the canvas and pointer coordinates aligned with their visible area.
