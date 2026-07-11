/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Many2XAutocomplete } from "@web/views/fields/relational_utils";
import { Many2OneField, many2OneField } from "@web/views/fields/many2one/many2one_field";

/**
 * Custom Many2XAutocomplete that opens the full search dialog directly
 * when the field has no value, instead of showing a small dropdown.
 * This gives the same UX as Many2many "Add a line" popup.
 */
class DialogMany2XAutocomplete extends Many2XAutocomplete {
    setup() {
        super.setup();
        this._dialogOpen = false;
    }

    async loadOptionsSource(request) {
        // When no value is set, open the full search dialog directly
        if (!this.props.value && !this._dialogOpen) {
            this._dialogOpen = true;
            this.onSearchMore(request);
            setTimeout(() => { this._dialogOpen = false; }, 500);
            return [];
        }
        // When a value exists, use normal autocomplete behavior
        if (this.props.value) {
            return super.loadOptionsSource(request);
        }
        return [];
    }
}

/**
 * Custom Many2One field widget that opens the search dialog directly
 * when the field is empty. Used for lot selection in the contact form.
 */
export class LotDialogMany2One extends Many2OneField {
    static components = {
        ...Many2OneField.components,
        Many2XAutocomplete: DialogMany2XAutocomplete,
    };
}

export const lotDialogMany2One = {
    ...many2OneField,
    component: LotDialogMany2One,
};

registry.category("fields").add("lot_dialog", lotDialogMany2One);
