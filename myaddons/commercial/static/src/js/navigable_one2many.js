/** @odoo-module */

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { useService } from "@web/core/utils/hooks";

/**
 * Generic One2many widget that navigates to the record's form view
 * in full page instead of opening a dialog.
 * Provides proper breadcrumb navigation.
 */
class NavigableOne2ManyField extends X2ManyField {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    async openRecord(record) {
        if (record.resId) {
            await this.actionService.doAction({
                type: "ir.actions.act_window",
                res_model: this.props.record.fields[this.props.name].relation,
                res_id: record.resId,
                views: [[false, "form"]],
                target: "current",
            });
        } else {
            super.openRecord(record);
        }
    }
}

const navigableOne2ManyField = {
    ...x2ManyField,
    component: NavigableOne2ManyField,
};

registry.category("fields").add("navigable_one2many", navigableOne2ManyField);
