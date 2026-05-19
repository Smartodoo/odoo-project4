/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

export class ClientLocationAutreLotSearchBar extends Component {
    static template = "commercial.ClientLocationAutreLotSearchBar";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            projetId: "",
            blocId: "",
            etageId: "",
            projets: [],
            blocs: [],
            etages: [],
        });

        onMounted(async () => {
            await this._loadProjets();
            await this._initFromRecord();
        });
    }

    async _initFromRecord() {
        const rec = this.props.record.data;
        if (rec.commercial_autre_projet_id) {
            const pid = rec.commercial_autre_projet_id[0] || rec.commercial_autre_projet_id;
            this.state.projetId = pid;
            await this._loadBlocs(pid);

            if (rec.commercial_autre_bloc_id) {
                const bid = rec.commercial_autre_bloc_id[0] || rec.commercial_autre_bloc_id;
                this.state.blocId = bid;
                await this._loadEtages(bid);

                if (rec.commercial_autre_etage_id) {
                    const eid = rec.commercial_autre_etage_id[0] || rec.commercial_autre_etage_id;
                    this.state.etageId = eid;
                }
            }
        }
    }

    async _loadProjets() {
        // Récupérer l'ID du type "Location"
        const typeLocation = await this.orm.searchRead(
            "commercial.type.projet",
            [["name", "=", "Location"]],
            ["id"],
            { limit: 1 }
        );
        const locationTypeId = typeLocation.length ? typeLocation[0].id : false;
        // Projets de type NON location
        const domain = locationTypeId ? ["!", ["type_projet_ids", "in", [locationTypeId]]] : [];
        const projets = await this.orm.searchRead(
            "commercial.projet", domain, ["name"], { order: "name" }
        );
        this.state.projets = projets.map((p) => ({ id: p.id, name: p.name }));
    }

    async _loadBlocs(projetId) {
        const domain = projetId ? [["projet_id", "=", projetId]] : [];
        const blocs = await this.orm.searchRead(
            "commercial.bloc", domain, ["name"], { order: "name" }
        );
        this.state.blocs = blocs.map((b) => ({ id: b.id, name: b.name }));
    }

    async _loadEtages(blocId) {
        const domain = blocId ? [["bloc_id", "=", blocId]] : [];
        const etages = await this.orm.searchRead(
            "commercial.etage", domain, ["etiquette"], { order: "sequence, id" }
        );
        this.state.etages = etages.map((e) => ({ id: e.id, name: e.etiquette || "" }));
    }

    _m2oValue(id, list) {
        if (!id) return false;
        const item = list.find((i) => i.id === id);
        return item ? [id, item.name] : false;
    }

    async _updateRecordFields() {
        await this.props.record.update({
            commercial_autre_projet_id: this._m2oValue(this.state.projetId, this.state.projets),
            commercial_autre_bloc_id: this._m2oValue(this.state.blocId, this.state.blocs),
            commercial_autre_etage_id: this._m2oValue(this.state.etageId, this.state.etages),
        });
    }

    async onProjetChange(ev) {
        this.state.projetId = ev.target.value ? parseInt(ev.target.value) : "";
        this.state.blocId = "";
        this.state.etageId = "";
        this.state.etages = [];
        if (this.state.projetId) {
            await this._loadBlocs(this.state.projetId);
        } else {
            this.state.blocs = [];
        }
        await this._updateRecordFields();
    }

    async onBlocChange(ev) {
        this.state.blocId = ev.target.value ? parseInt(ev.target.value) : "";
        this.state.etageId = "";
        if (this.state.blocId) {
            await this._loadEtages(this.state.blocId);
        } else {
            this.state.etages = [];
        }
        await this._updateRecordFields();
    }

    async onEtageChange(ev) {
        this.state.etageId = ev.target.value ? parseInt(ev.target.value) : "";
        await this._updateRecordFields();
    }

    async onClear() {
        this.state.projetId = "";
        this.state.blocId = "";
        this.state.etageId = "";
        this.state.blocs = [];
        this.state.etages = [];
        await this._updateRecordFields();
    }

    get hasActiveFilter() {
        return this.state.projetId || this.state.blocId || this.state.etageId;
    }
}

registry.category("view_widgets").add("client_location_autre_lot_search_bar", {
    component: ClientLocationAutreLotSearchBar,
});
