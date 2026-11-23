/** @odoo-module **/
// Rapports Auberge : bouton « Imprimer PDF » dans le tableau croisé.
// Le tableau est imprimé tel qu'il est affiché (filtres, regroupements,
// mesures), comme l'export Excel standard.
import { download } from "@web/core/network/download";
import { registry } from "@web/core/registry";
import { pivotView } from "@web/views/pivot/pivot_view";
import { PivotRenderer } from "@web/views/pivot/pivot_renderer";

export class HotelPivotPdfRenderer extends PivotRenderer {
    async onPrintPdfClicked() {
        const table = this.model.exportData();
        const facets = this.env.searchModel ? this.env.searchModel.facets : [];
        table.filters = facets.map((f) => [...f.values].join(` ${f.separator || "ou"} `));
        // Type de chaque mesure (montant, décimal, entier) pour le formatage
        const { activeMeasures, fields } = this.model.metaData;
        table.measure_types = activeMeasures.map((m) =>
            m === "__count" ? "integer" : (fields[m] && fields[m].type) || "float");
        table.report_title = (this.env.config.getDisplayName && this.env.config.getDisplayName())
            || table.title;
        await download({
            url: "/hotel/pivot/pdf",
            data: { data: new Blob([JSON.stringify(table)], { type: "application/json" }) },
        });
    }
}

registry.category("views").add("hotel_pivot_pdf", {
    ...pivotView,
    Renderer: HotelPivotPdfRenderer,
    buttonTemplate: "hotel_management.PivotPdfButtons",
});
