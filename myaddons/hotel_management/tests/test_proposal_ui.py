from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestProposalUi(HttpCase):
    """Nouvelle réservation (écran) : les chambres / lits déjà occupés ne
    figurent pas dans la liste de choix des lignes."""

    def test_taken_not_listed(self):
        self.env.ref('base.user_admin').password = 'admin'
        ci = fields.Date.today()
        co = ci + timedelta(days=2)
        rtype = self.env['hotel.room.type'].create({'name': 'Type UI', 'list_price': 3000})
        room = self.env['hotel.room'].create({
            'name': 'ZZTAKEN', 'room_type_id': rtype.id, 'capacity': 2,
            'room_price': 3000, 'rental_mode': 'room'})
        partner = self.env['res.partner'].create({'name': 'Client UI', 'hotel_birthdate': '1990-01-01'})
        resa = self.env['hotel.reservation'].create({
            'partner_id': partner.id, 'checkin': ci, 'checkout': co,
            'line_ids': [(0, 0, {'room_id': room.id, 'price_unit': 3000})]})
        resa.action_confirm()
        self.browser_js(
            '/odoo/action-hotel_management.action_hotel_reservation/new',
            r'''
            const wait = (sel, cb, n = 0) => {
                const el = typeof sel === 'function' ? sel() : document.querySelector(sel);
                if (el) { cb(el); } else if (n > 60) { console.error('timeout ' + sel); }
                else { setTimeout(() => wait(sel, cb, n + 1), 250); }
            };
            const add = [...document.querySelectorAll(".o_notebook .tab-pane.active .o_field_x2many_list_row_add :is(a,button)")][0];
            add.click();
            wait(".tab-pane.active .o_data_row .o_field_widget[name='room_id'] input", (input) => {
                input.value = 'ZZTAKEN';
                input.dispatchEvent(new Event('input', {bubbles: true}));
                setTimeout(() => {
                    const items = [...document.querySelectorAll('.o-autocomplete--dropdown-menu li')]
                        .map((li) => li.textContent.trim());
                    console.log('ITEMS ' + JSON.stringify(items));
                    if (items.some((t) => t.includes('ZZTAKEN'))) {
                        console.error('Chambre occupée proposée : ' + JSON.stringify(items));
                    } else {
                        document.querySelector('.o_form_button_cancel')?.click();
                        console.log('test successful');
                    }
                }, 2500);
            });
            ''',
            ready="!!document.querySelector('.o_form_view .o_field_x2many_list_row_add :is(a,button)')",
            login='admin', timeout=90)
