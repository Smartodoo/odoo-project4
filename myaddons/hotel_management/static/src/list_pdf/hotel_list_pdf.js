/** @odoo-module **/
// Rapports Auberge : bouton « Imprimer PDF » dans la vue liste.
// Imprime tous les enregistrements correspondant aux filtres, avec les
// colonnes affichées, les regroupements et les totaux.
import { download } from "@web/core/network/download";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

export class HotelListPdfController extends ListController {
    async onPrintPdfClicked() {
        // Un seul PDF à la fois : un double clic occupait les 2 workers
        // (wkhtmltopdf) et bloquait tout le serveur jusqu'au timeout.
        if (this._hotelPdfPrinting) {
            return;
        }
        this._hotelPdfPrinting = true;
        this.env.services.ui.block();
        try {
            await this._hotelPrintPdf();
        } finally {
            this.env.services.ui.unblock();
            this._hotelPdfPrinting = false;
        }
    }

    async _hotelPrintPdf() {
        const root = this.rootRef();
        const archColumns = {};
        for (const col of this.props.archInfo.columns) {
            if (col.type === "field") {
                archColumns[col.name] = col;
            }
        }
        const columns = [...root.querySelectorAll(".o_list_table thead th[data-name]")]
            .map((th) => ({
                name: th.dataset.name,
                label: th.textContent.trim(),
                sum: Boolean(archColumns[th.dataset.name]?.attrs?.sum),
            }))
            .filter((c) => c.name in archColumns);
        const list = this.model.root;
        const facets = this.env.searchModel ? this.env.searchModel.facets : [];
        const payload = {
            model: this.props.resModel,
            domain: list.domain,
            group_by: list.groupBy || [],
            order: (list.orderBy || []).map((o) => `${o.name} ${o.asc ? "asc" : "desc"}`).join(", "),
            columns,
            filters: facets.map((f) => [...f.values].join(` ${f.separator || "ou"} `)),
            title: (this.env.config.getDisplayName && this.env.config.getDisplayName()) || "",
        };
        await download({
            url: "/hotel/list/pdf",
            data: { data: new Blob([JSON.stringify(payload)], { type: "application/json" }) },
        });
    }
}

registry.category("views").add("hotel_list_pdf", {
    ...listView,
    Controller: HotelListPdfController,
    buttonTemplate: "hotel_management.ListPdfButtons",
});
