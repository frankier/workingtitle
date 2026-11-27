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
