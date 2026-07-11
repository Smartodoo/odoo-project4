/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class RentalDashboard extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.state = useState({
            kpi: {
                ongoing_count: 0,
                monthly_revenue: 0,
                available_count: 0,
                expiring_count: 0
            }
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        const data = await this.rpc("/web/dataset/call_kw/rental.dashboard/get_revenue_data", {
            model: 'rental.dashboard',
            method: 'get_revenue_data',
            args: ['month'],
            kwargs: {},
        });
        if (data && data.kpi) {
            this.state.kpi = data.kpi;
        }
    }
}

RentalDashboard.template = "rental_management.RentalDashboardTemplate";

// On enregistre l'action pour qu'elle soit utilisable dans le XML
registry.category("actions").add("rental_dashboard_action", RentalDashboard);