/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class HotelDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, loading: true });
        onWillStart(() => this.loadData());
    }

    async loadData() {
        this.state.loading = true;
        this.state.data = await this.orm.call(
            "hotel.reservation",
            "get_dashboard_data",
            []
        );
        this.state.loading = false;
    }

    formatAmount(value) {
        const data = this.state.data || {};
        const nb = new Intl.NumberFormat("fr-FR", {
            maximumFractionDigits: 0,
        }).format(value || 0);
        return `${nb} ${data.currency_symbol || ""}`.trim();
    }

    openRooms(domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name || "Chambres",
            res_model: "hotel.room",
            domain: domain || [],
            views: [
                [false, "kanban"],
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
        });
    }

    openReservations(domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name || "Réservations",
            res_model: "hotel.reservation",
            domain: domain || [],
            views: [
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
        });
    }

    openModel(model, domain, name, kanban) {
        const views = kanban
            ? [[false, "kanban"], [false, "list"], [false, "form"]]
            : [[false, "list"], [false, "form"]];
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: model,
            domain: domain || [],
            views: views,
            target: "current",
        });
    }

    openReservation(resId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "hotel.reservation",
            res_id: resId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

HotelDashboard.template = "hotel_management.Dashboard";

registry.category("actions").add("hotel_dashboard", HotelDashboard);
