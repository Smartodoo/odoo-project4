/** @odoo-module */

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

class LotsParProjetListController extends ListController {
    async onClickNouveauLot() {
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Nouveau Lot",
            res_model: "commercial.lot",
            views: [[false, "form"]],
            target: "current",
        });
    }
}

const lotsParProjetListView = {
    ...listView,
    Controller: LotsParProjetListController,
    buttonTemplate: "commercial.LotsParProjetListButtons",
};

registry.category("views").add("lots_par_projet_list", lotsParProjetListView);