import { patch } from "@web/core/utils/patch";
import { FormCompiler } from "@web/views/form/form_compiler";

import "@mail/chatter/web/form_compiler";

const LAYOUT_CALL = "__comp__.mailLayout(true)";

/**
 * mail's FormCompiler patch replaces the t-if of the attachment preview with
 * `mailLayout(true) == "COMBO"`, dropping the view's `invisible` modifier.
 * Re-inject that modifier: every `mailLayout(true)` call becomes
 * `mailLayout(<preview is visible>)`, so a hidden preview behaves as if the
 * form had no preview at all (normal side/bottom chatter, no preview pane).
 */
patch(FormCompiler.prototype, {
    compile(key, params = {}) {
        const res = super.compile(key, params);
        const previewArch = this.templates[key]?.querySelector?.("div.o_attachment_preview");
        const invisible = previewArch?.getAttribute("invisible");
        if (!invisible || invisible === "False" || invisible === "0") {
            return res;
        }
        const recordExpr = params.recordExpr || "__comp__.props.record";
        const visibleExpr =
            invisible === "True" || invisible === "1"
                ? "false"
                : `!__comp__.evaluateBooleanExpr(${JSON.stringify(
                      invisible
                  )},${recordExpr}.evalContextWithVirtualIds)`;
        const replacement = `__comp__.mailLayout(${visibleExpr})`;
        for (const el of [res, ...res.querySelectorAll("*")]) {
            for (const attr of [...el.attributes]) {
                if (attr.value.includes(LAYOUT_CALL)) {
                    el.setAttribute(attr.name, attr.value.split(LAYOUT_CALL).join(replacement));
                }
            }
        }
        return res;
    },
});
