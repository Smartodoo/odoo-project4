/** @odoo-module **/
import { useService } from "@web/core/utils/hooks";

import { CalendarController } from "@web/views/calendar/calendar_controller";
import { patch } from "@web/core/utils/patch";


patch(CalendarController.prototype, {
    setup(...args) {
        super.setup(...args)
        this.actionService = useService("action");
    },
    _onClickRefreshView (ev) { 
        this.actionService.switchView('calendar');
    }
  
});
