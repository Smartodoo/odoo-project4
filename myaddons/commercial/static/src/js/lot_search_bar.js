/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { useService } from "@web/core/utils/hooks";

export class LotSearchBar extends Component {
    static template = "commercial.LotSearchBar";
    static props = { ...standardWidgetProps };

    setup() {
        this.state = useState({
            numeroLot: "",
            bloc: "",
            etage: "",
            categorie: "",
            stateFilter: "",
        });
        this.rootRef = useRef("root");
        this._observer = null;
        this._debounceTimer = null;
        this.actionService = useService("action");
        this.orm = useService("orm");

        onMounted(() => {
            setTimeout(() => this._setupObserver(), 300);
        });

        onWillUnmount(() => {
            if (this._observer) this._observer.disconnect();
            if (this._debounceTimer) clearTimeout(this._debounceTimer);
        });
    }

    _getListContainer() {
        const el = this.rootRef.el;
        if (!el) return null;
        const page = el.closest(".tab-pane") || el.closest(".o_notebook_content") || el.closest(".o_form_sheet");
        return page ? page.querySelector(".o_field_one2many") : null;
    }

    _setupObserver() {
        const container = this._getListContainer();
        if (!container) return;
        this._observer = new MutationObserver(() => {
            clearTimeout(this._debounceTimer);
            this._debounceTimer = setTimeout(() => this._applyFilter(), 150);
        });
        this._observer.observe(container, { childList: true, subtree: true });
    }

    _getCellText(row, colIndex) {
        const cells = row.querySelectorAll("td.o_data_cell");
        if (colIndex < cells.length) {
            return cells[colIndex].textContent.trim().toLowerCase();
        }
        return "";
    }

    // Columns: 0=N° Lot, 1=Code perso, 2=Bloc, 3=Étage, 4=Catégorie, 5=Surface, 6=Montant, 7=Statut
    _applyFilter() {
        const container = this._getListContainer();
        if (!container) return;

        const filters = {
            numeroLot: this.state.numeroLot.toLowerCase().trim(),
            bloc: this.state.bloc.toLowerCase().trim(),
            etage: this.state.etage.toLowerCase().trim(),
            categorie: this.state.categorie.toLowerCase().trim(),
            stateFilter: this.state.stateFilter,
        };
        const STATE_LABELS = {
            disponible: "disponible",
            en_option: "pré-réservé",
            reserve: "réservé",
            vendu: "vendu",
        };

        const rows = container.querySelectorAll(".o_data_row");
        rows.forEach((row) => {
            let visible = true;

            if (filters.numeroLot && !this._getCellText(row, 0).includes(filters.numeroLot)) {
                visible = false;
            }
            if (visible && filters.bloc && !this._getCellText(row, 2).includes(filters.bloc)) {
                visible = false;
            }
            if (visible && filters.etage && !this._getCellText(row, 3).includes(filters.etage)) {
                visible = false;
            }
            if (visible && filters.categorie && !this._getCellText(row, 4).includes(filters.categorie)) {
                visible = false;
            }
            if (visible && filters.stateFilter) {
                const badge = row.querySelector(".badge");
                const badgeText = badge ? badge.textContent.trim().toLowerCase() : "";
                if (badgeText !== STATE_LABELS[filters.stateFilter]) {
                    visible = false;
                }
            }

            row.style.display = visible ? "" : "none";
        });
    }

    onInput(field, ev) {
        this.state[field] = ev.target.value;
        this._applyFilter();
    }

    onStateChange(ev) {
        this.state.stateFilter = ev.target.value;
        this._applyFilter();
    }

    onClear() {
        this.state.numeroLot = "";
        this.state.bloc = "";
        this.state.etage = "";
        this.state.categorie = "";
        this.state.stateFilter = "";
        this._applyFilter();
    }

    get hasActiveFilter() {
        return this.state.numeroLot || this.state.bloc || this.state.etage
            || this.state.categorie || this.state.stateFilter;
    }

    async onPrint() {
        const projetId = this.props.record.resId;
        if (!projetId) return;

        const filters = {
            bloc: this.state.bloc.trim() || false,
            etage: this.state.etage.trim() || false,
            categorie: this.state.categorie.trim() || false,
            numero_lot: this.state.numeroLot.trim() || false,
            state: this.state.stateFilter || false,
        };

        const action = await this.orm.call(
            "commercial.projet",
            "action_print_liste_lots_filtered",
            [[projetId], filters],
        );

        if (action) {
            this.actionService.doAction(action);
        }
    }
}

registry.category("view_widgets").add("lot_search_bar", {
    component: LotSearchBar,
});
