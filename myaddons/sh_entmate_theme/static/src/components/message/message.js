/* @odoo-module */
import { user } from "@web/core/user";

import { patch } from "@web/core/utils/patch";
import { Message } from "@mail/core/common/message";
import { session } from "@web/session";
const components = { Message };

patch(components.Message.prototype, {

    // Odoo 20: extend core attClass instead of copying it (core keys changed; author is author_id)
    get attClass() {
        const author = this.props.message?.author_id || this.props.message?.author;
        const isLoginUser = Boolean(author && user.partnerId == author.id);
        return {
            ...super.attClass,
            'sh_right_chat': isLoginUser,
            'sh_left_chat': !isLoginUser,
        };
    },

});