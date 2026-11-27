"""Controls shared by plot workspaces."""

from bokeh.models import GroupBox, InlineStyleSheet

from workingtitle_bokeh.help_icon import HelpIcon

__all__ = ["HelpIcon", "control_group"]


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
