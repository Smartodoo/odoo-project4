/* @odoo-module */
import { user } from "@web/core/user";

import { Component, onWillStart, proxy, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { rpc } from "@web/core/network/rpc";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";

export class LanguageTemplate extends Component {
       static components = { Dropdown };
       static template = "LanguageTemplate";

       setup() {
            this.actionService = useService("action");
            this.orm = useService("orm");
            this.state = proxy({ languages_list: [], selected_lang: user.context.lang });
            onWillStart(async () => {
                await this.check_language_enabled();
                await this.fetch_sh_get_installed_lang();
            });
        }

       async check_language_enabled() {
            const data = await this.orm.searchRead(
            "res.users",
            [['id', '=', user.userId]],
            ["sh_enable_language_selection"]
            );

            if (data) {
                if (! data[0].sh_enable_language_selection) {
                    $('.sh_language_selector').hide();
                    }
            }
       }

       async fetch_sh_get_installed_lang() {
            const languages = await rpc("/web/dataset/call_kw/res.lang/sh_get_installed_lang", {
                    model: 'res.lang',
                    method: 'sh_get_installed_lang',
                    args: [],
                    kwargs: {},
                });
            this.state.languages_list = languages || [];
            this.state.selected_lang = user.context.lang;
       }

       async onBeforeOpen() {
        await this.fetch_sh_get_installed_lang();
        }

       change_sh_user_lang(e){
            var self = this;
            var lang = e[0]
            var self = this;

            this.orm.write("res.users", [parseInt(user.userId)], { 'lang': lang }).then(function () {
            self.actionService.doAction({
                        name: 'Reload Context',
                        type: 'ir.actions.client',
                        tag: 'reload_context',
                    });
        });
        }
}

registry.category("systray").add("sh_entmate_theme.language_template", { Component: LanguageTemplate });