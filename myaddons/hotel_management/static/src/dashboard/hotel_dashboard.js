/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, proxy } from "@odoo/owl";

export class HotelDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({
            data: null,
            loading: true,
            preset: "today",
            dateFrom: "",
            dateTo: "",
            periodError: "",
        });
        this.applyPreset("today", false);
        onWillStart(() => this.loadData());
    }

    async loadData() {
        this.state.loading = true;
        this.state.data = await this.orm.call("hotel.reservation", "get_dashboard_data", [], {
            date_from: this.state.dateFrom || false,
            date_to: this.state.dateTo || false,
        });
        this.state.loading = false;
    }

    // ------------------------------------------------------------------
    // Période du bloc « Sur la période »
    // ------------------------------------------------------------------
    static PRESETS = [
        ["today", "Aujourd'hui"],
        ["7days", "7 derniers jours"],
        ["month", "Ce mois"],
        ["last_month", "Mois dernier"],
        ["year", "Cette année"],
    ];

    get presets() {
        return HotelDashboard.PRESETS;
    }

    isoDate(date) {
        const pad = (n) => String(n).padStart(2, "0");
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
    }

    applyPreset(preset, reload = true) {
        const today = new Date();
        const y = today.getFullYear();
        const m = today.getMonth();
        let from = today;
        let to = today;
        if (preset === "7days") {
            from = new Date(y, m, today.getDate() - 6);
        } else if (preset === "month") {
            from = new Date(y, m, 1);
        } else if (preset === "last_month") {
            from = new Date(y, m - 1, 1);
            to = new Date(y, m, 0);
        } else if (preset === "year") {
            from = new Date(y, 0, 1);
        }
        this.state.preset = preset;
        this.state.dateFrom = this.isoDate(from);
        this.state.dateTo = this.isoDate(to);
        this.state.periodError = "";
        if (reload) {
            this.loadData();
        }
    }

    onDateChange(field, ev) {
        this.state[field] = ev.target.value;
        this.state.preset = "custom";
        const { dateFrom, dateTo } = this.state;
        if (!dateFrom || !dateTo) {
            this.state.periodError = "Choisissez les deux dates.";
            return;
        }
        if (dateFrom > dateTo) {
            this.state.periodError = "La date « du » doit être avant la date « au ».";
            return;
        }
        this.state.periodError = "";
        this.loadData();
    }

    get periodLabel() {
        return (this.state.data && this.state.data.period && this.state.data.period.label) || "";
    }

    openPeriodPayments() {
        const p = this.state.data.period;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: `Encaissements (${p.label})`,
            res_model: "account.payment",
            domain: [
                ["hotel_reservation_id", "!=", false],
                ["state", "in", ["paid", "reconciled"]],
                ["date", ">=", p.start],
                ["date", "<=", p.end],
            ],
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    formatAmount(value) {
        const data = this.state.data || {};
        const nb = new Intl.NumberFormat("fr-FR", {
            maximumFractionDigits: 0,
        }).format(value || 0);
        return `${nb} ${data.currency_symbol || ""}`.trim();
    }

    /** Ids des enregistrements comptés par une tuile (cf. get_dashboard_data). */
    tileIds(key) {
        const ids = (this.state.data && this.state.data.tile_ids) || {};
        return ids[key] || [];
    }

    /** Ouvre exactement les enregistrements comptés par la tuile `key`. */
    openTile(model, key, name) {
        const domain = [["id", "in", this.tileIds(key)]];
        if (model === "hotel.room") {
            return this.openRooms(domain, name);
        }
        if (model === "hotel.reservation") {
            return this.openReservations(domain, name);
        }
        if (model === "hotel.bed") {
            return this.openModel(model, domain, name, false);
        }
        return this.openModel(model, domain, name, true);
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

    openPlanning() {
        this.action.doAction("hotel_management.action_hotel_planning");
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
