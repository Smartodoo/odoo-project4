/** @odoo-module */

import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { onMounted } from "@odoo/owl";

class LotsParProjetFormController extends FormController {
    setup() {
        super.setup();
        onMounted(async () => {
            if (this.model.root && !this.model.root.isNew) {
                await this.model.root.switchMode("edit");
            }
        });
    }

    async discard() {
        await super.discard(...arguments);
        // Re-enter edit mode after discarding so add/delete buttons stay visible
        if (this.model.root && !this.model.root.isNew) {
            await this.model.root.switchMode("edit");
        }
    }
}

const lotsParProjetFormView = {
    ...formView,
    Controller: LotsParProjetFormController,
};

registry.category("views").add("lots_par_projet_form", lotsParProjetFormView);