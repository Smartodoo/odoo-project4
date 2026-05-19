/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

export class ClientSearchBar extends Component {
    static template = "commercial.ClientSearchBar";
    static props = { ...standardWidgetProps };

    setup() {
        this.state = useState({
            nom: "",
            bloc: "",
        });
        this.rootRef = useRef("root");
        this._observer = null;
        this._debounceTimer = null;

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
        return page ? page.querySelector(".o_field_one2many, .o_field_many2many") : null;
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

    // Columns: 0=Nom, 1=Téléphone, 2=Email, 3=Projet, 4=Bloc, 5=Lots
    _applyFilter() {
        const container = this._getListContainer();
        if (!container) return;

        const nom = this.state.nom.toLowerCase().trim();
        const bloc = this.state.bloc.toLowerCase().trim();

        const rows = container.querySelectorAll(".o_data_row");
        rows.forEach((row) => {
            let visible = true;

            if (nom && !this._getCellText(row, 0).includes(nom)) {
                visible = false;
            }
            if (visible && bloc && !this._getCellText(row, 4).includes(bloc)) {
                visible = false;
            }

            row.style.display = visible ? "" : "none";
        });
    }

    onInput(field, ev) {
        this.state[field] = ev.target.value;
        this._applyFilter();
    }

    onClear() {
        this.state.nom = "";
        this.state.bloc = "";
        this._applyFilter();
    }

    get hasActiveFilter() {
        return this.state.nom || this.state.bloc;
    }
}

registry.category("view_widgets").add("client_search_bar", {
    component: ClientSearchBar,
});