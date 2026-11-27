"""Placement controls and responsive behavior for two-panel workspaces."""

from dataclasses import dataclass
from urllib.parse import quote

from bokeh.events import DocumentReady
from bokeh.models import CustomJS, Div, InlineStyleSheet, RadioButtonGroup

from .browser import ON_FRAME


_PLACEMENTS = {
    "sidebar": ("Right sidebar", "M14 2h4v16h-4z"),
    "bottom": ("Bottom", "M2 11h16v7H2z"),
    "right": ("Right (half width)", "M10 2h8v16h-8z"),
}


class PlacementSelector:
    """A native single-choice Bokeh widget with icon buttons and named placements."""

    def __init__(
        self, placements=tuple(_PLACEMENTS), *, placement=None, name=None, panel=None
    ):
        self._placements = tuple(placements)
        if not self._placements or len(set(self._placements)) != len(self._placements):
            raise ValueError("Supply one or more distinct placements")
        labels = []
        rules = [
            """
            .bk-btn-group { gap: 2px; }
            .bk-btn { font-size: 0; padding: 4px; width: 32px; height: 32px; }
            .bk-btn::before { content: ""; display: inline-block; width: 18px;
                height: 18px; background: currentColor; }
        """
        ]
        for i, mode in enumerate(self._placements, start=1):
            if mode not in _PLACEMENTS:
                raise ValueError(f"Unknown placement: {mode!r}")
            label, path = _PLACEMENTS[mode]
            labels.append(label)
            svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">'
                '<rect x="1" y="1" width="18" height="18" rx="2" '
                'fill="none" stroke="black" stroke-width="1.5"/>'
                f'<path d="{path}"/></svg>'
            )
            rules.append(
                f'.bk-btn:nth-child({i})::before {{ mask: url("data:image/svg+xml,{quote(svg)}") center/contain no-repeat; }}'
            )
        initial = self._placements[0] if placement is None else placement
        self.widget = RadioButtonGroup(
            labels=labels,
            active=self._placements.index(initial),
            stylesheets=[InlineStyleSheet(css="\n".join(rules))],
            width=len(labels) * 34 - 2,
            height=32,
            margin=0,
            name=name,
            visible=panel is None or panel.visible,
        )

        if panel is not None:
            panel.js_link("visible", self.widget, "visible")
            panel.on_change("visible", self._panel_visibility_changed)

    def _panel_visibility_changed(self, attr, old, visible):
        self.widget.visible = visible

    @property
    def placement(self):
        return self._placements[self.widget.active]

    @placement.setter
    def placement(self, value):
        self.widget.active = self._placements.index(value)

    def on_change(self, callback):
        """Call callback(placement) when the selected placement changes."""
        self.widget.on_change(
            "active", lambda attr, old, new: callback(self._placements[new])
        )


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


class ResponsivePanels:
    """Measure a mounted workspace and remember its preferences per fullscreen mode."""

    def __init__(
        self,
        doc,
        frame,
        *,
        breakpoint=900,
        normal=None,
        fullscreen=None,
        name=None,
        host_selector=None,
    ):
        self.breakpoint = breakpoint
        self.normal = normal if normal is not None else PanelMode()
        self.fullscreen = (
            fullscreen if fullscreen is not None else PanelMode(left=False)
        )
        self.viewport = Div(text="1440,900", visible=False, name=name)
        doc.js_on_event(
            DocumentReady,
            CustomJS(
                args=dict(
                    frame=frame, viewport=self.viewport, host_selector=host_selector
                ),
                code=ON_FRAME
                + """
                const view = Bokeh.index.find_one(frame);
                if (!view) return;
                const el = view.el;
                const host = host_selector && el.closest(host_selector);
                const update = () => onFrame(el, 'workingtitleViewportFrame', () => {
                    const {top, width} = el.getBoundingClientRect();
                    const available = Math.floor(width);
                    const size = `${available},${window.innerHeight}`;
                    if (available > 0 && viewport.text !== size) viewport.text = size;
                    const offset = `${top}px`;
                    if (el.style.getPropertyValue('--workspace-top') !== offset)
                        el.style.setProperty('--workspace-top', offset);
                });
                const observer = new ResizeObserver(update);
                observer.observe(el);
                observer.observe(host || document.body);
                const lifetime = new AbortController();
                view.removed.connect(() => { observer.disconnect(); lifetime.abort(); });
                window.addEventListener('resize', update, {signal: lifetime.signal});
                document.addEventListener('fullscreenchange', update, {signal: lifetime.signal});
                update();
            """,
            ),
        )

    @property
    def narrow(self):
        width, _ = self.viewport.text.split(",")
        return int(width) < self.breakpoint

    @property
    def viewport_height(self):
        _, height = self.viewport.text.split(",")
        return int(height)

    def mode(self, full):
        return self.fullscreen if full else self.normal

    def fit(self, full):
        mode = self.mode(full)
        mode.fit(self.narrow)
        return mode

    def toggle(self, full, side, active):
        self.mode(full).toggle(side, active, self.narrow)
