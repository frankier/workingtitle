"""Integration tests for the optional Bokeh package (Python 3.12+)."""

import pytest

pytest.importorskip("bokeh", minversion="3.10")

from bokeh.document import Document
from bokeh.layouts import column
from bokeh.models import Div

from workingtitle.bokeh.panels import PlacementSelector, ResponsivePanels
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


def test_workspace_breakpoint_and_per_mode_placement():
    panels = ResponsivePanels(Document(), column(Div()), breakpoint=720)
    panels.viewport.text = "720,900"
    panels.toggle(False, "right", True)
    assert panels.normal.left and panels.normal.right
    panels.viewport.text = "719,900"
    assert not panels.fit(False).left
    panels.toggle(False, "left", True)
    assert panels.normal.left and not panels.normal.right
    panels.toggle(False, "right", True)
    panels.normal.place("bottom")
    panels.toggle(False, "left", True)
    assert panels.normal.left and panels.normal.right
    assert panels.fullscreen.placement == "sidebar"
    assert not panels.fullscreen.left and not panels.fullscreen.right


def test_observe_named_placement_in_supplied_order():
    selector = PlacementSelector(("bottom", "right"), placement="right")
    changes = []
    selector.on_change(changes.append)
    selector.widget.active = 0
    assert selector.placement == "bottom"
    selector.placement = "bottom"
    selector.placement = "right"
    assert changes == ["bottom", "right"]
    with pytest.raises(ValueError):
        selector.placement = "sidebar"
