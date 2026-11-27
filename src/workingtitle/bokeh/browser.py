"""Browser callback fragments for frame-aligned controls."""

ON_FRAME = """
function onFrame(owner, key, update) {
    if (owner[key]) return;
    owner[key] = requestAnimationFrame(() => {
        owner[key] = null;
        update();
    });
}
"""

ON_PLOT_FRAME = (
    ON_FRAME
    + """
function onPlotFrame(owner, key, findPlot, update) {
    onFrame(owner, key, () => {
        const plot = findPlot();
        const view = plot && Bokeh.index.find_one(plot);
        const box = view?.frame?.bbox;
        if (box?.width > 0 && box.height > 0) update(view, box);
    });
}
"""
)
