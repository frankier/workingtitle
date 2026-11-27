'use strict';
/*!
 * Copyright (c) Anaconda, Inc., and Bokeh Contributors
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without modification,
 * are permitted provided that the following conditions are met:
 *
 * Redistributions of source code must retain the above copyright notice,
 * this list of conditions and the following disclaimer.
 *
 * Redistributions in binary form must reproduce the above copyright notice,
 * this list of conditions and the following disclaimer in the documentation
 * and/or other materials provided with the distribution.
 *
 * Neither the name of Anaconda nor the names of any contributors
 * may be used to endorse or promote products derived from this software
 * without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
 * LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF
 * THE POSSIBILITY OF SUCH DAMAGE.
 */
(function(root, factory) {
  factory(root["Bokeh"], undefined);
})(this, function(Bokeh, version) {
  let define;
  return (function(modules, entry, aliases, externals) {
    const bokeh = typeof Bokeh !== "undefined" ? (version != null ? Bokeh[version] : Bokeh) : null;
    if (bokeh != null) {
      return bokeh.register_plugin(modules, entry, aliases);
    } else {
      throw new Error("Cannot find Bokeh" + (version != null ? " " + version : "") + ". You have to load it prior to loading plugins.");
    }
  })
({
"8b5f1d48d0": /* index.js */ function _(require, module, exports, __esModule, __esExport) {
    __esModule();
    const base_1 = require("@bokehjs/base");
    const help_icon_1 = require("bce15b7788") /* ./help_icon */;
    (0, base_1.register_models)({ HelpIcon: help_icon_1.HelpIcon });
},
"bce15b7788": /* help_icon.js */ function _(require, module, exports, __esModule, __esExport) {
    __esModule();
    const widget_1 = require("@bokehjs/models/widgets/widget");
    const tooltip_1 = require("@bokehjs/models/ui/tooltip");
    const builtin_icon_1 = require("@bokehjs/models/ui/icons/builtin_icon");
    const build_views_1 = require("@bokehjs/core/build_views");
    class AdjacentTooltipView extends tooltip_1.TooltipView {
        _reposition() {
            // Bokeh computes viewport coordinates but moves tooltips to body on
            // every update. Restore this tooltip beside its trigger afterwards.
            super._reposition();
            this.target.after(this.el);
            if (this.model.visible && this.model.position != null) {
                // Moving a popover closes it; reopen it in the top layer so fixed
                // positioning still works inside Bokeh's contained layouts.
                this.el.showPopover?.();
            }
        }
    }
    class HelpIconView extends widget_1.WidgetView {
        tooltip_view;
        icon_view;
        children_views() {
            return [...super.children_views(), this.tooltip_view, this.icon_view];
        }
        async lazy_initialize() {
            await super.lazy_initialize();
            this.tooltip_view = await (0, build_views_1.build_view)(this.model.tooltip, { parent: this }, () => AdjacentTooltipView);
            this.icon_view = await (0, build_views_1.build_view)(new builtin_icon_1.BuiltinIcon({ icon_name: "help", size: 18 }), {
                parent: this,
            });
        }
        render() {
            super.render();
            const button = document.createElement("button");
            button.type = "button";
            button.setAttribute("aria-label", this.model.accessible_label);
            button.style.cssText =
                "display:block;width:18px;height:18px;padding:0;border:0;background:transparent;color:inherit;cursor:help";
            this.icon_view.render();
            button.append(this.icon_view.el);
            this.shadow_el.append(button);
            this.tooltip_view.target = button;
            let hovered = false;
            let focused = false;
            const update = () => (this.model.tooltip.visible = hovered || focused);
            button.addEventListener("mouseenter", () => {
                hovered = true;
                update();
            });
            button.addEventListener("mouseleave", () => {
                hovered = false;
                update();
            });
            button.addEventListener("focus", () => {
                focused = true;
                update();
            });
            button.addEventListener("blur", () => {
                focused = false;
                update();
            });
            button.addEventListener("keydown", (event) => {
                if (event.key === "Escape")
                    this.model.tooltip.visible = false;
            });
            this.tooltip_view.render();
            this.tooltip_view.r_after_render();
        }
        remove() {
            this.icon_view.remove();
            this.tooltip_view.remove();
            super.remove();
        }
    }
    exports.HelpIconView = HelpIconView;
    class HelpIcon extends widget_1.Widget {
        static __module__ = "workingtitle_bokeh.help_icon";
        static {
            this.prototype.default_view = HelpIconView;
            this.define(({ Ref, Str }) => ({ tooltip: [Ref(tooltip_1.Tooltip)], accessible_label: [Str, "Help"] }));
        }
    }
    exports.HelpIcon = HelpIcon;
},
}, "8b5f1d48d0", {"index":"8b5f1d48d0","help_icon":"bce15b7788"}, {});});
//# sourceMappingURL=workingtitle_bokeh.js.map
