/** @odoo-module */

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

class ClientProjetListController extends ListController {
    /**
     * Override openRecord to navigate to a standard res.partner list view
     * filtered by the clicked project. This gives full list features:
     * checkboxes, gear icon, actions (delete, email, SMS, etc.)
     */
    async openRecord(record) {
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            name: record.data.name || "Clients",
            res_model: "res.partner",
            view_mode: "tree,form",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["commercial_projet_id", "=", record.resId],
                ["type_client_commercial", "=", "client"],
            ],
            context: {
                default_contact_category: "interne",
                is_contact_externe: true,
                default_commercial_projet_id: record.resId,
            },
        });
    }

    async onClickNouveauClient() {
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Nouveau Client",
            res_model: "res.partner",
            views: [[false, "form"]],
            target: "current",
            context: {
                default_contact_category: "interne",
                is_contact_externe: true,
            },
        });
    }
}

const clientProjetListView = {
    ...listView,
    Controller: ClientProjetListController,
    buttonTemplate: "commercial.ClientProjetListButtons",
};

registry.category("views").add("client_projet_list", clientProjetListView);
