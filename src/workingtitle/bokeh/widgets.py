"""Controls shared by plot workspaces."""

from typing import TYPE_CHECKING

from bokeh.models import CheckboxGroup, GroupBox, InlineStyleSheet


if TYPE_CHECKING:
    from workingtitle_bokeh.help_icon import HelpIcon

__all__ = ["CHECKBOX_CSS", "HelpIcon", "checkbox", "enabled", "control_group"]


def __getattr__(name):
    # Bokeh servers include every registered extension in their page resources.
    # Apps that only build native control groups need no custom JavaScript.
    if name == "HelpIcon":
        from workingtitle_bokeh.help_icon import HelpIcon

        return HelpIcon
    raise AttributeError(name)


def control_group(title, child, *, scrolling=False, **kwargs):
    """Keep fieldsets shrinkable horizontally and optionally scroll at intrinsic height."""
    options = dict(width_policy="max", margin=(5, 0))
    if scrolling:
        child.width_policy = "max"
        child.height_policy = "min"
        options.update(
            height_policy="min", styles={"flex-shrink": "0", "max-height": "none"}
        )
    stylesheets = [InlineStyleSheet(css="fieldset { min-inline-size: 0; }")]
    stylesheets.extend(kwargs.pop("stylesheets", []))
    return GroupBox(
        title=title, child=child, stylesheets=stylesheets, **(options | kwargs)
    )


CHECKBOX_CSS = """
    .bk-input-group { white-space: normal; }
    label { display: flex; align-items: center; width: 100%; }
    input { flex-shrink: 0; }
    span { min-width: 0; overflow-wrap: anywhere; }
"""


def checkbox(label, checked=False, **options):
    """Create a one-option checkbox group with a wrapping label."""
    stylesheets = [InlineStyleSheet(css=CHECKBOX_CSS), *options.pop("stylesheets", [])]
    return CheckboxGroup(
        labels=[label],
        active=[0] if checked else [],
        stylesheets=stylesheets,
        **options,
    )


def enabled(checkbox):
    """Return the checked state of a one-option group."""
    return bool(checkbox.active)
