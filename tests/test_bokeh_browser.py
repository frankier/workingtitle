"""Exercise the distributed widget and workspace against the installed BokehJS."""

import pytest

pytest.importorskip("pytest_playwright")
pytest.importorskip("bokeh", minversion="3.10")

from bokeh.embed import file_html
from bokeh.layouts import column, row
from bokeh.resources import INLINE
from playwright.sync_api import expect

from workingtitle.bokeh.panels import PlacementSelector
from workingtitle.bokeh.widgets import HelpIcon
from workingtitle.bokeh.workspace import FrameFullscreen, Sidebar


def test_help_and_sidebar_across_fullscreen(page, tmp_path):
    help_icon = HelpIcon("Choose layers", accessible_label="Layer help")
    sidebar = Sidebar.create(
        help_icon,
        widths=(200, 40),
        button_widths=(110, 30),
        labels=("Hide controls", "Show controls"),
    )
    frame = column(row(sidebar.shell))
    fullscreen = FrameFullscreen(frame)
    sidebar.remember_in_browser(fullscreen)
    frame.children.append(fullscreen.button())
    path = tmp_path / "workspace.html"
    path.write_text(file_html(frame, INLINE))
    page.goto(path.as_uri())
    help_button = page.get_by_role("button", name="Layer help")
    tooltip = page.get_by_text("Choose layers", exact=True)
    help_button.hover()
    expect(tooltip).to_be_visible()
    help_button.focus()
    help_button.press("Escape")
    expect(tooltip).to_be_hidden()
    page.get_by_role("button", name="Fullscreen").click()
    expect(help_button).to_be_hidden()
    page.get_by_text("Show controls", exact=True).click()
    help_button.focus()
    expect(tooltip).to_be_visible()
    assert help_button.evaluate("el => el.nextElementSibling?.matches('[popover]')")
    page.evaluate("document.exitFullscreen()")
    expect(help_button).to_be_visible()
    page.get_by_text("Hide controls", exact=True).click()
    page.get_by_role("button", name="Fullscreen").click()
    expect(help_button).to_be_visible()
    page.evaluate("document.exitFullscreen()")
    expect(help_button).to_be_hidden()


def test_placement_icons_and_keyboard_selection(page, tmp_path):
    selector = PlacementSelector(("right", "bottom"))
    path = tmp_path / "placements.html"
    path.write_text(file_html(selector.widget, INLINE))
    page.goto(path.as_uri())
    bottom = page.get_by_role("button", name="Bottom", exact=True)
    right = page.get_by_role("button", name="Right (half width)", exact=True)
    expect(page.get_by_role("button")).to_have_count(2)
    for button in (right, bottom):
        assert button.evaluate(
            "el => getComputedStyle(el, '::before').maskImage"
        ).startswith('url("data:image/svg+xml,')
    bottom.focus()
    bottom.press("Enter")
    bottom.click()
    expect(page.locator("button.bk-active")).to_have_text("Bottom")


def test_scrollbar_fits_each_edge_and_follows_external_zoom(page, tmp_path):
    from bokeh.models import Range1d
    from workingtitle.bokeh.ranges import range_scrollbar

    axis = Range1d(2, 5, min_interval=3, name="axis")
    track = range_scrollbar(axis, (0, 10), name="track")
    path = tmp_path / "scrollbar.html"
    path.write_text(file_html(track, INLINE))
    page.goto(path.as_uri())
    page.wait_for_function("window.Bokeh?.documents[0]?.is_idle")
    for value, expected in [([0, 1], [0, 3]), ([9, 10], [7, 10]), ([4, 5], [3, 6])]:
        page.evaluate(
            "v => Bokeh.documents[0].get_model_by_name('track').value = v", value
        )
        page.wait_for_function(
            """([lo, hi]) => {
            const d = Bokeh.documents[0], axis = d.get_model_by_name("axis");
            const [a, b] = d.get_model_by_name("track").value;
            return axis.start === lo && axis.end === hi && a === lo && b === hi;
        }""",
            arg=expected,
        )
    page.evaluate("Bokeh.documents[0].get_model_by_name('axis').setv({start:1,end:8})")
    page.wait_for_function(
        "Bokeh.documents[0].get_model_by_name('track').value.join() === '1,8'"
    )


def test_slow_range_consumer_receives_only_latest_pending_value(page, tmp_path):
    from types import SimpleNamespace
    from bokeh.document import Document
    from bokeh.models import RangeSlider
    from workingtitle.bokeh.sliders import on_range_commit

    doc = Document()
    slider = RangeSlider(name="slider", start=0, end=10, value=(0, 10))
    # Manually acknowledge requests to hold the first one in flight.
    on_range_commit(
        SimpleNamespace(session_context=object(), js_on_event=doc.js_on_event),
        slider,
        lambda low, high: None,
        pause_ms=10,
        name="requests",
    )
    doc.add_root(slider)
    path = tmp_path / "commits.html"
    path.write_text(file_html(doc, INLINE))
    page.goto(path.as_uri())
    page.wait_for_function("window.Bokeh?.documents[0]?.is_idle")
    page.evaluate("""() => {
        window.slider = Bokeh.documents[0].get_model_by_name('slider');
        window.requests = Bokeh.documents[0].get_model_by_name('requests');
        slider.value = [1, 8];
    }""")
    page.wait_for_function("requests.text === '[1,1,8]'")
    page.evaluate("""async () => {
        slider.value = [2, 8];
        await new Promise(resolve => setTimeout(resolve, 50));
        slider.value = [3, 8];
        await new Promise(resolve => setTimeout(resolve, 50));
    }""")
    assert page.evaluate("requests.text") == "[1,1,8]"
    page.evaluate("requests.tags = [1]")
    page.wait_for_function("requests.text === '[2,3,8]'")
