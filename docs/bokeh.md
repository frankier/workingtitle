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

### Responsive panels and placement buttons

A workspace with two panels can use the same breakpoint for its sidebar CSS
and its open/closed policy. The controller measures the frame itself, so a
narrow embedded frame behaves the same way as a narrow browser window.

```python
from workingtitle.bokeh.panels import PlacementSelector, ResponsivePanels

panels = ResponsivePanels(doc, frame, breakpoint=800)
selector = PlacementSelector(("sidebar", "bottom", "right"), panel=details)
details_header.children.append(selector.widget)

def place_details(placement):
    full = fullscreen.state.text == "full"
    panels.mode(full).place(placement)
    # Render the active mode in the application's mounted panel containers.
    render_panels(panels.fit(full))

selector.on_change(place_details)
```

Pass the side (`"left"` or `"right"`) to `panels.toggle(full, side, active)`,
then apply the mode. Reapply on changes to `panels.viewport.text` and
`fullscreen.state.text`. When reflecting mode state into toggles, guard their
callbacks so a programmatic update is not treated as a user request. Below
the breakpoint, opening one rail closes the other. A bottom panel can coexist
with the left rail. Normal and fullscreen modes retain separate preferences.

The selector accepts an ordered subset of placements. Pass the details panel
to keep its buttons visible only while the panel is open. Its accessible buttons
support mouse and keyboard selection, including standalone HTML. In a server
document, `on_change` receives the selected placement name. Applications
choose when details open and which content to show.

The two-panel `apply_layout` helper accepts the mounted frame, body, workspace,
center, left/right columns, content columns and toggles as attributes of one
object. It supports viewport, contained and page sizing.

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
