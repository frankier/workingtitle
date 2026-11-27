"""Fullscreen controls and collapsible panels for mounted Bokeh layouts."""

from dataclasses import dataclass
from typing import Literal, Protocol

from .browser import ON_FRAME

from bokeh.events import DocumentReady
from bokeh.layouts import column
from bokeh.models import (
    BuiltinIcon,
    Button,
    Column,
    LayoutDOM,
    Row,
    CustomAction,
    CustomJS,
    Div,
    FullscreenTool,
    InlineStyleSheet,
    Toggle,
)


class FrameFullscreen:
    """Bind toolbar actions and buttons to the same frame and observable mode."""

    def __init__(
        self,
        frame,
        *,
        document=None,
        state=None,
        dialogs=(),
        overflow="auto",
        padding=8,
    ):
        self.state = Div(text="normal", visible=False) if state is None else state
        frame.stylesheets = [
            *frame.stylesheets,
            InlineStyleSheet(
                css=f"""
            :host {{ background: white }}
            :host(:fullscreen) {{ width: 100vw !important; height: 100vh !important;
                overflow: {overflow}; padding: {padding}px; box-sizing: border-box }}
        """
            ),
        ]
        args = dict(viewer_frame=frame, state=self.state, dialogs=list(dialogs))
        observe = """
            const view = Bokeh.index.find_one(viewer_frame);
            const element = view?.el;
            if (!element) return;
            if (!element.workingtitleFullscreen) {
                element.workingtitleFullscreen = () => {
                    const full = document.fullscreenElement === element;
                    const mode = full ? "full" : "normal";
                    if (state.text === mode) return;
                    state.text = mode;
                    for (const dialog of dialogs) {
                        const el = Bokeh.index.find_one(dialog)?.el;
                        if (dialog.visible && el) (full ? view.shadow_el : document.body).append(el);
                    }
                };
                element.addEventListener("fullscreenchange", element.workingtitleFullscreen);
                element.workingtitleFullscreen();
            }
        """
        if document is not None:
            document.js_on_event(DocumentReady, CustomJS(args=args, code=observe))
        self.callback = CustomJS(
            args=args,
            code=observe
            + """
            if (document.fullscreenElement === element) void document.exitFullscreen();
            else if (!document.fullscreenElement) void element.requestFullscreen();
        """,
        )
        for dialog in dialogs:
            dialog.js_on_change(
                "visible",
                CustomJS(
                    args=dict(dialog=dialog, frame=frame),
                    code="""
                queueMicrotask(() => {
                    const view = Bokeh.index.find_one(frame);
                    if (view && dialog.visible && document.fullscreenElement === view.el) {
                        const el = Bokeh.index.find_one(dialog)?.el;
                        if (el) view.shadow_el.append(el);
                    }
                });
            """,
                ),
            )

    def button(self, **options):
        button = Button(label="Fullscreen", icon=BuiltinIcon("fullscreen"), **options)
        button.js_on_click(self.callback)
        return button

    def action(self):
        return CustomAction(
            description="Fullscreen", icon="fullscreen", callback=self.callback
        )


def prepare_toolbar(plot):
    """Add a native single-plot fullscreen action."""
    plot.toolbar.logo = None
    plot.add_tools(FullscreenTool())


@dataclass
class Sidebar:
    """A collapsible rail whose toggle and content stay in the document."""

    shell: Column
    content: LayoutDOM
    toggle: Toggle
    widths: tuple[int, int]
    labels: tuple[str, str]
    button_widths: tuple[int, int]

    @classmethod
    def create(
        cls,
        content,
        *,
        widths,
        labels,
        button_widths,
        active=True,
        toggle_options=None,
        shell_options=None,
    ):
        toggle = Toggle(active=active, **(toggle_options or {}))
        shell = column(toggle, content, **(shell_options or {}))
        sidebar = cls(shell, content, toggle, widths, labels, button_widths)
        sidebar.show(active)
        return sidebar

    def show(self, active):
        index = 0 if active else 1
        self.toggle.active = self.content.visible = active
        self.shell.width = self.widths[index]
        self.toggle.width = self.button_widths[index]
        self.toggle.label = self.labels[index]

    def remember_in_browser(
        self, fullscreen, *, normal_open=True, fullscreen_open=False
    ):
        """Apply independent normal and fullscreen preferences without a server round trip."""
        modes = [
            Toggle(active=normal_open, name="normal-sidebar-open"),
            Toggle(active=fullscreen_open, name="fullscreen-sidebar-open"),
        ]
        self.show(normal_open)
        sync = CustomJS(
            args=dict(
                state=fullscreen.state,
                toggle=self.toggle,
                controls_sidebar=self.content,
                shell=self.shell,
                modes=modes,
                widths=self.widths,
                labels=self.labels,
                button_widths=self.button_widths,
            ),
            code="""
            const mode = modes[state.text === "full" ? 1 : 0];
            if (cb_obj === toggle) mode.active = toggle.active;
            const open = mode.active, i = open ? 0 : 1;
            controls_sidebar.visible = toggle.active = open;
            shell.width = widths[i];
            toggle.label = labels[i];
            toggle.width = button_widths[i];
        """,
        )
        self.toggle.js_on_change("active", sync)
        fullscreen.state.js_on_change("text", sync)


@dataclass
class PanelMode:
    """The two-panel preferences for one display mode."""

    left: bool = True
    right: bool = False
    placement: str = "sidebar"

    def fit(self, narrow):
        if narrow and self.right and self.placement != "bottom":
            self.left = False

    def toggle(self, side, active, narrow):
        if side == "left":
            self.left = active
            if active and self.placement != "bottom":
                self.placement = "sidebar"
                if narrow:
                    self.right = False
        else:
            self.right = active
            self.placement = "sidebar"
        self.fit(narrow)

    def place(self, placement):
        self.placement = placement
        if placement == "right":
            self.left = False


SCROLL_STYLES = {
    "min-height": "0",
    "min-width": "0",
    "overflow": "auto",
    "overscroll-behavior": "contain",
    "flex": "1",
}


class TwoPanelLayout(Protocol):
    """Mounted components used to lay out controls, central plots and details."""

    frame: Column
    body: Row
    workspace: Row
    center: Column
    left: Column
    right: Column
    left_controls: Column
    right_controls: Column
    left_toggle: Toggle
    right_toggle: Toggle


def observe_panel_width(doc, panel):
    """Recompute Bokeh canvas geometry after the flex panel reaches its new width."""
    doc.js_on_event(
        DocumentReady,
        CustomJS(
            args=dict(panel=panel),
            code=ON_FRAME
            + """
            const view = Bokeh.index.find_one(panel);
            if (!view || view.el.workingtitleWidthObserver) return;
            let previousWidth = view.el.getBoundingClientRect().width;
            const observer = new ResizeObserver(([entry]) => {
                const width = entry.borderBoxSize[0].inlineSize;
                if (!width || width === previousWidth) return;
                previousWidth = width;
                onFrame(view, 'workingtitleLayoutFrame', () => {
                    if (view.el.isConnected) view.compute_layout();
                });
            });
            view.el.workingtitleWidthObserver = observer;
            observer.observe(view.el, {box: "border-box"});
        """,
        ),
    )


def apply_layout(
    ui: TwoPanelLayout,
    layout: Literal["viewport", "contained", "page"],
    *,
    full=False,
    bottom=False,
    container="workspace",
    viewport_height="100dvh",
    collapsed_width=38,
):
    """Keep all pane geometry in one inherited CSS update."""
    page = layout == "page" and not full
    flow = {"min-height": "0", "min-width": "0"}
    height = "auto" if page else "100%"
    scrolling = {**flow, "overflow": "visible"} if page else SCROLL_STYLES
    ui.frame.styles = {
        **flow,
        "height": (
            "auto"
            if page
            else "100%"
            if layout == "contained" and not full
            else viewport_height
        ),
        "box-sizing": "border-box",
        "overflow": "visible" if page else "hidden",
    }
    left, right = ui.left_toggle.active, ui.right_toggle.active
    ui.body.styles = {
        **flow,
        "height": height,
        "position": "relative",
        "container-type": "inline-size",
        "container-name": container,
        "--workspace-direction": "column" if bottom else "row",
        "--controls-position": "relative" if left else "absolute",
        "--controls-width": f"{ui.left.width}px",
        "--controls-height": height if left else "auto",
        "--controls-layer": "auto" if left else "10",
        "--details-position": "relative" if right else "absolute",
        "--details-width": f"{collapsed_width}px"
        if not right
        else None
        if ui.right.width is not None
        else "100%"
        if bottom
        else "auto",
        "--details-flex": "1 1 0px"
        if right and ui.right.width is None and not bottom
        else "0 0 auto",
        "--details-height": height if right and not bottom else "auto",
        "--details-max-height": "50%" if bottom and not page else "none",
        "--details-border": "1px solid #cbd5e1" if bottom else "0",
        "--details-padding": "8px" if bottom else "0",
        "--details-layer": "auto" if right else "10",
    }
    ui.workspace.styles = {
        **flow,
        "height": height,
        "position": "relative",
        "flex-direction": "var(--workspace-direction)",
    }
    ui.left.styles = {
        **flow,
        "position": "var(--controls-position)",
        "top": "0",
        "left": "0",
        "width": "var(--controls-width)",
        "height": "var(--controls-height)",
        "flex": "0 0 auto",
        "z-index": "var(--controls-layer)",
    }
    ui.right.styles = {
        **flow,
        "position": "var(--details-position)",
        "top": "0",
        "right": "0",
        "width": "var(--details-width, var(--sidebar-width))",
        "height": "var(--details-height)",
        "max-height": "var(--details-max-height)",
        "border-top": "var(--details-border)",
        "padding-top": "var(--details-padding)",
        "flex": "var(--details-flex)",
        "z-index": "var(--details-layer)",
        "box-sizing": "border-box",
    }
    ui.left_controls.styles = ui.right_controls.styles = scrolling
    ui.center.styles = {**scrolling, "flex": "1 1 0px"}
