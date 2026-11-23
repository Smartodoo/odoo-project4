/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, proxy } from "@odoo/owl";

/**
 * Tableau de bord de la caisse : tout ce que le responsable doit voir
 * d'un coup d'œil (caisse ouverte, encaissements du jour par mode, mois en
 * cours, écarts, 7 derniers jours, dernières opérations et fermetures).
 * Données : caisse.session.get_dashboard_data().
 */
export class CaisseDashboard extends Component {
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
        this.state.data = await this.orm.call("caisse.session", "get_dashboard_data", [], {
            date_from: this.state.dateFrom || false,
            date_to: this.state.dateTo || false,
        });
        this.state.loading = false;
    }

    // ------------------------------------------------------------------
    // Période des statistiques
    // ------------------------------------------------------------------
    static PRESETS = [
        ["today", "Aujourd'hui"],
        ["7days", "7 derniers jours"],
        ["month", "Ce mois"],
        ["last_month", "Mois dernier"],
        ["year", "Cette année"],
    ];

    get presets() {
        return CaisseDashboard.PRESETS;
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

    periodDomain(field = "day") {
        const p = this.data.month || {};
        return [[field, ">=", p.start], [field, "<=", p.end]];
    }

    get data() {
        return this.state.data || {};
    }

    fmt(value) {
        const nb = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(value || 0);
        return `${nb} ${this.data.currency_symbol || ""}`.trim();
    }

    fmtSigned(value) {
        return (value > 0 ? "+" : "") + this.fmt(value);
    }

    fmtDate(value) {
        if (!value) {
            return "";
        }
        // "YYYY-MM-DD HH:MM:SS" -> "DD/MM HH:MM"
        const [d, t] = value.split(" ");
        const [, m, day] = d.split("-");
        return `${day}/${m}${t ? " " + t.slice(0, 5) : ""}`;
    }

    barHeight(value) {
        const max = this.data.max_day || 1;
        return `height: ${Math.max(2, Math.round((value / max) * 100))}%`;
    }

    gapClass(value) {
        if (value < 0) {
            return "text-danger";
        }
        return value > 0 ? "text-warning" : "text-success";
    }

    kindClass(kind) {
        if (["payment", "in", "float", "purchase_refund"].includes(kind)) {
            return "o_cd_in";
        }
        return kind === "transfer" ? "o_cd_transfer" : "o_cd_out";
    }

    // ------------------------------------------------------------------
    // Actions
    // ------------------------------------------------------------------
    async quickMove(method) {
        const current = this.data.current;
        if (!current) {
            return;
        }
        const action = await this.orm.call("caisse.session", method, [[current.id]]);
        this.action.doAction(action, { onClose: () => this.loadData() });
    }

    openCurrent() {
        this.action.doAction("caisse.action_caisse_current");
    }

    openSession(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "caisse.session",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openSessions(domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name || "Sessions de caisse",
            res_model: "caisse.session",
            domain: domain || [],
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    openJournal(domain, name, context) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name || "Journal de caisse",
            res_model: "caisse.journal",
            domain: domain || [],
            context: context || {},
            views: [[false, "list"], [false, "pivot"], [false, "graph"]],
            target: "current",
        });
    }

    openJournalLine(id) {
        this.orm.call("caisse.journal", "action_open_source", [[id]]).then((action) =>
            this.action.doAction(action)
        );
    }

    openToday(kinds, name) {
        const domain = [["day", "=", this.data.today_iso]];
        if (kinds) {
            domain.push(["kind", "in", kinds]);
        }
        this.openJournal(domain, name);
    }

    openMonth(kinds, name) {
        const domain = this.periodDomain();
        if (kinds) {
            domain.push(["kind", "in", kinds]);
        }
        this.openJournal(domain, `${name} (${this.data.month.label})`);
    }

    openDay(bucket) {
        const fr = (iso) => iso.split("-").reverse().join("/");
        if (bucket.day === bucket.day_to) {
            this.openJournal([["day", "=", bucket.day]], `Journal du ${fr(bucket.day)}`);
        } else {
            this.openJournal(
                [["day", ">=", bucket.day], ["day", "<=", bucket.day_to]],
                `Journal du ${fr(bucket.day)} au ${fr(bucket.day_to)}`
            );
        }
    }

    openTodayPayments(mode, label) {
        const domain = [
            ["hotel_reservation_id", "!=", false],
            ["date", "=", this.data.today_iso],
            ["state", "in", ["paid", "reconciled"]],
        ];
        if (mode) {
            domain.push(["hotel_payment_mode", "=", mode]);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: label ? `Paiements du jour — ${label}` : "Paiements du jour",
            res_model: "account.payment",
            domain,
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    openMissingProof() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Sorties sans justificatif",
            res_model: "caisse.move",
            domain: [
                ["move_type", "!=", "in"],
                ["attachment", "=", false],
                ["date", ">=", this.data.month.start + " 00:00:00"],
                ["date", "<=", this.data.month.end + " 23:59:59"],
            ],
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

}

CaisseDashboard.template = "caisse.Dashboard";

registry.category("actions").add("caisse_dashboard", CaisseDashboard);
