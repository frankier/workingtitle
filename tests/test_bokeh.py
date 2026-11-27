"""Integration tests for the optional Bokeh package (Python 3.12+)."""

import pytest

pytest.importorskip("bokeh", minversion="3.10")

from bokeh.layouts import column
from bokeh.models import Div

from workingtitle.bokeh.widgets import HelpIcon, control_group
from workingtitle.bokeh.workspace import FrameFullscreen, PanelMode, Sidebar


def test_frame_and_controls():
    content = control_group("Settings", column(Div()), scrolling=True)
    sidebar = Sidebar.create(
        content, widths=(200, 40), button_widths=(100, 30), labels=("Hide", "Show")
    )
    frame = column(sidebar.shell)
    fullscreen = FrameFullscreen(frame)
    sidebar.remember_in_browser(fullscreen)
    assert (
        fullscreen.action().callback
        is fullscreen.button().js_event_callbacks["button_click"][0]
    )
    sidebar.show(False)
    assert sidebar.shell.children == [sidebar.toggle, content]
    assert not content.visible
    assert sidebar.shell.width == 40


def test_panel_placement_at_narrow_width():
    panels = PanelMode()
    panels.toggle("right", True, narrow=True)
    assert panels.right and not panels.left
    panels.toggle("left", True, narrow=True)
    assert panels.left and not panels.right
    panels.right = True
    panels.place("bottom")
    panels.fit(narrow=True)
    assert panels.left and panels.right


def test_help_widget_wheel_resources():
    from bokeh.embed import file_html
    from bokeh.resources import INLINE

    html = file_html(HelpIcon("Choose layers", accessible_label="Layer help"), INLINE)
    assert "class AdjacentTooltipView" in html
    assert "Layer help" in html
