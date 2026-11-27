"""Viewport fitting and browser-side range navigation for ascending numeric axes."""

from math import isfinite

from bokeh.models import CustomJS, InlineStyleSheet, RangeSlider


def fit_viewport(viewport, bounds, *, min_interval=0):
    """Fit a saved interval into bounds, expanding about its center if necessary."""
    lower, upper = bounds
    if not (isfinite(lower) and isfinite(upper) and lower < upper):
        raise ValueError("bounds must be finite and increasing")
    if not isfinite(min_interval) or min_interval < 0:
        raise ValueError("min_interval must be finite and nonnegative")
    start, end = viewport
    span = end - start
    if not isfinite(span) or span < 0 or (span == 0 and min_interval == 0):
        return lower, upper
    width = max(span, min_interval)
    if width >= upper - lower:
        return lower, upper
    if width > span:
        start -= (width - span) / 2
        end = start + width
    if start < lower:
        return lower, lower + width
    if end > upper:
        return upper - width, upper
    return start, end


def update_reset_range(plot_range, start, end):
    """Follow a changing data extent until zoomed; always update the Reset target."""
    if plot_range.reset_start is None or (plot_range.start, plot_range.end) == (
        plot_range.reset_start,
        plot_range.reset_end,
    ):
        plot_range.update(start=start, end=end)
    plot_range.update(reset_start=start, reset_end=end)


def range_scrollbar(
    plot_range, bounds, orientation="horizontal", min_interval=None, *, name=None
):
    """Link a Range1d and a scrollbar in both directions without a server round trip."""
    if orientation not in ("horizontal", "vertical"):
        raise ValueError("orientation must be horizontal or vertical")
    floor = plot_range.min_interval if min_interval is None else min_interval
    if floor is None:
        floor = 0
    start, end = fit_viewport(
        (plot_range.start, plot_range.end), bounds, min_interval=floor
    )
    plot_range.update(start=start, end=end)
    vertical = orientation == "vertical"
    scrollbar = RangeSlider(
        name=name or f"{orientation}-range-scrollbar",
        start=bounds[0],
        end=bounds[1],
        value=(start, end),
        step=max((bounds[1] - bounds[0]) / 10_000, 1e-12),
        orientation=orientation,
        direction="rtl" if vertical else "ltr",
        show_value=False,
        tooltips=False,
        bar_color="#d1d5db",
        width=28 if vertical else 100,
        height=100 if vertical else 28,
        margin=0,
        sizing_mode="fixed",
        stylesheets=[
            InlineStyleSheet(
                css="""
            :host { overflow: visible !important; }
            .bk-slider-title { display: none !important; }
            .bk-input-group {
                box-sizing: border-box !important;
                height: 100% !important;
                padding: 0 !important;
                overflow: visible !important;
            }
            .noUi-target { border: 0 !important; }
            .noUi-target.noUi-vertical {
                flex: 1 1 auto !important;
                height: 100% !important;
                min-height: 0 !important;
                margin: 0 10px !important;
            }
            .noUi-target.noUi-horizontal {
                margin: 10px 0 !important;
                width: 100% !important;
            }
            .noUi-vertical .noUi-handle {
                top: auto !important;
                bottom: var(--handle-right) !important;
            }
        """
            )
        ],
    )
    scrollbar.js_on_change(
        "value",
        CustomJS(
            args={
                "plot_range": plot_range,
                "floor": floor,
            },
            code="""
        let [start, end] = cb_obj.value
        if (start === plot_range.start && end === plot_range.end) return
        const lower = cb_obj.start, upper = cb_obj.end
        const span = end - start
        // Mirror fit_viewport for browser-only slider gestures.
        const width = Math.max(span, floor)
        if (span < 0 || width === 0 || width >= upper - lower) {
            start = lower
            end = upper
        } else if (width > span) {
            start -= (width - span) / 2
            end = start + width
        }
        if (start < lower) { start = lower; end = lower + width }
        if (end > upper) { end = upper; start = upper - width }
        plot_range.setv({start, end})
        if (cb_obj.value[0] !== start || cb_obj.value[1] !== end)
            cb_obj.value = [start, end]
    """,
        ),
    )
    sync = CustomJS(
        args={"scrollbar": scrollbar, "plot_range": plot_range},
        code="""
        const [start, end] = scrollbar.value
        if (start !== plot_range.start || end !== plot_range.end)
            scrollbar.value = [plot_range.start, plot_range.end]
    """,
    )
    plot_range.js_on_change("start", sync)
    plot_range.js_on_change("end", sync)
    return scrollbar
