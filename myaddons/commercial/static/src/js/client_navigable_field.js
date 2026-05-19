/** @odoo-module */

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { useService } from "@web/core/utils/hooks";

/**
 * Custom One2many widget that navigates to the record's form view
 * instead of opening an inline dialog. This ensures proper breadcrumb
 * navigation (Project → Client → Versements).
 */
class ClientNavigableX2ManyField extends X2ManyField {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    async openRecord(record) {
        const resId = record.resId;
        if (resId) {
            await this.actionService.doAction({
                type: "ir.actions.act_window",
                name: record.data.display_name || record.data.name || "Contact",
                res_model: this.props.record.fields[this.props.name].relation,
                views: [[false, "form"]],
                res_id: resId,
                target: "current",
                context: {
                    default_contact_category: "interne",
                    is_contact_externe: true,
                },
            });
        } else {
            // New record: fall back to default dialog behavior
            super.openRecord(record);
        }
    }
}

const clientNavigableX2ManyField = {
    ...x2ManyField,
    component: ClientNavigableX2ManyField,
};

registry.category("fields").add("client_navigable_one2many", clientNavigableX2ManyField);