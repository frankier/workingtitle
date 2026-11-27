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
    details = Div(visible=False)
    selector = PlacementSelector(("bottom", "right"), placement="right", panel=details)
    assert not selector.widget.visible
    details.visible = True
    assert selector.widget.visible
    changes = []
    selector.on_change(changes.append)
    selector.widget.active = 0
    assert selector.placement == "bottom"
    selector.placement = "bottom"
    selector.placement = "right"
    assert changes == ["bottom", "right"]
    with pytest.raises(ValueError):
        selector.placement = "sidebar"


@pytest.mark.parametrize(
    ("viewport", "floor", "expected"),
    [
        ((2, 2.1), 0.75, (1.675, 2.425)),
        ((0, 0.2), 0.75, (0, 0.75)),
        ((4.8, 4.9), 0.75, (4.24, 4.99)),
        ((0, 4.99), 0.75, (0, 4.99)),
        ((2, 3), 10, (0, 4.99)),
        ((5, 7), 0, (2.99, 4.99)),
        ((-3, -1), 0, (0, 2)),
        ((2, 3), 0, (2, 3)),
    ],
)
def test_fit_viewport(viewport, floor, expected):
    from workingtitle.bokeh.ranges import fit_viewport

    assert fit_viewport(viewport, (0, 4.99), min_interval=floor) == pytest.approx(
        expected
    )


def test_zoomed_range_keeps_view_and_updates_reset_target():
    from bokeh.models import Range1d
    from workingtitle.bokeh.ranges import update_reset_range

    axis = Range1d(0, 10)
    update_reset_range(axis, 0, 20)
    assert (axis.start, axis.end) == (0, 20)
    axis.update(start=3, end=7)
    update_reset_range(axis, 1, 9)
    assert (axis.start, axis.end) == (3, 7)
    assert (axis.reset_start, axis.reset_end) == (1, 9)


def test_commit_validation_and_acknowledgement():
    from types import SimpleNamespace
    from bokeh.models import RangeSlider
    from workingtitle.bokeh.sliders import on_range_commit

    delivered = []

    def receive(lo, hi):
        delivered.append((lo, hi))
        if lo == 2:
            raise RuntimeError("callback failed")

    doc = Document()
    slider = RangeSlider(start=0, end=10, value=(0, 10))
    on_range_commit(
        SimpleNamespace(session_context=object(), js_on_event=doc.js_on_event),
        slider,
        receive,
        name="requests",
    )
    doc.add_root(slider)
    requests = doc.get_model_by_name("requests")
    requests.text = "[1, 1, 5]"
    requests.text = "[1, 2, 5]"
    requests.text = "[2, -1, 4]"
    assert delivered == [(1, 5)]
    assert requests.tags == [2]
    with pytest.raises(RuntimeError):
        requests.text = "[3, 2, 4]"
    assert requests.tags == [3]
    slider.value = (3, 5)
    assert delivered[-1] == (3, 5)
