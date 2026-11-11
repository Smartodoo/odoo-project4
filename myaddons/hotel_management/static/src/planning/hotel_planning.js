/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, proxy } from "@odoo/owl";

/**
 * Planning graphique de l'auberge (cahier des charges §3.3) :
 * chambres (et lits des dortoirs) en lignes, jours en colonnes,
 * réservations en barres colorées selon leur état.
 */
export class HotelPlanning extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({
            data: null,
            loading: true,
            dateFrom: this.isoDate(new Date()),
            days: 14,
        });
        onWillStart(() => this.load());
    }

    isoDate(d) {
        const pad = (n) => String(n).padStart(2, "0");
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }

    shift(nbDays) {
        const d = new Date(this.state.dateFrom + "T00:00:00");
        d.setDate(d.getDate() + nbDays);
        this.state.dateFrom = this.isoDate(d);
        return this.load();
    }

    goToday() {
        this.state.dateFrom = this.isoDate(new Date());
        return this.load();
    }

    setDays(ev) {
        this.state.days = parseInt(ev.target.value, 10) || 14;
        return this.load();
    }

    setDate(ev) {
        if (ev.target.value) {
            this.state.dateFrom = ev.target.value;
            return this.load();
        }
    }

    async load() {
        this.state.loading = true;
        this.state.data = await this.orm.call(
            "hotel.planning",
            "get_planning_data",
            [this.state.dateFrom, this.state.days]
        );
        this.state.loading = false;
    }

    /** Répartit les barres d'une ligne en couloirs pour éviter les chevauchements. */
    lanes(bookings) {
        const lanes = [];
        const sorted = [...bookings].sort((a, b) => a.start - b.start);
        for (const b of sorted) {
            let lane = lanes.find((l) => l[l.length - 1].end <= b.start);
            if (!lane) {
                lane = [];
                lanes.push(lane);
            }
            lane.push(b);
        }
        return lanes.length ? lanes : [[]];
    }

    gridStyle() {
        return `grid-template-columns: repeat(${this.state.data.days.length}, minmax(44px, 1fr));`;
    }

    barStyle(b) {
        return `grid-column: ${b.start + 1} / ${b.end + 1};`;
    }

    barTitle(b) {
        let title = `${b.name} — ${b.partner}\n${b.checkin} → ${b.checkout}\n${b.state_label}`;
        if (b.beds && b.booking_type === "bed") {
            title += `\nLit(s) : ${b.beds}`;
        }
        return title;
    }

    openReservation(resId) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "hotel.reservation",
                res_id: resId,
                views: [[false, "form"]],
                target: "current",
            },
            { onClose: () => this.load() }
        );
    }

    newReservation(room, dayIndex) {
        const day = this.state.data.days[dayIndex];
        const next = new Date(day.date + "T00:00:00");
        next.setDate(next.getDate() + 1);
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "hotel.reservation",
            views: [[false, "form"]],
            target: "current",
            context: {
                default_checkin: day.date,
                default_checkout: this.isoDate(next),
                default_booking_type: room.rental_mode === "bed" ? "bed" : "room",
                default_line_ids: [[0, 0, { room_id: room.id }]],
            },
        });
    }

    openRoom(roomId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "hotel.room",
            res_id: roomId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

HotelPlanning.template = "hotel_management.Planning";

registry.category("actions").add("hotel_planning", HotelPlanning);
