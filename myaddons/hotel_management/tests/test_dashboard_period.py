from datetime import date

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDashboardPeriod(TransactionCase):
    """Tableau de bord : bloc « Sur la période » (du / au)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        rtype = cls.env['hotel.room.type'].create({'name': 'Type période', 'list_price': 1000})
        cls.room = cls.env['hotel.room'].create({
            'name': 'DP-1', 'room_type_id': rtype.id, 'capacity': 3,
            'rental_mode': 'bed', 'bed_price': 1000, 'room_price': 3000})
        partner = cls.env['res.partner'].create({'hotel_last_name': 'Test', 'hotel_first_name': 'Client', 'phone': '0550000009', 'street': '1 rue Test', 'hotel_id_type': 'cni', 'hotel_id_number': 'ID-T', 'name': 'Client période', 'hotel_birthdate': '1990-01-01'})
        # 2 lits du 10 au 13/01/2091 : 3 nuits x 2 places = 6 nuitées
        cls.resa = cls.env['hotel.reservation'].create({
            'partner_id': partner.id, 'checkin': date(2091, 1, 10), 'checkout': date(2091, 1, 13),
            'booking_type': 'bed', 'children': 1, 'line_ids': [
                (0, 0, {'bed_id': cls.room.bed_ids[0].id}),
                (0, 0, {'bed_id': cls.room.bed_ids[1].id})]})
        cls.resa.action_confirm()

    def _data(self, start, end):
        return self.env['hotel.reservation'].get_dashboard_data(start, end)

    def test_full_period(self):
        data = self._data('2091-01-01', '2091-01-31')
        self.assertEqual(data['period']['days'], 31)
        self.assertEqual(data['period']['nights'], 6)
        self.assertIn(self.resa.id, data['tile_ids']['month_reservations'])
        self.assertEqual(data['month_reservations'], 1)
        self.assertGreater(data['period']['bed_rate'], 0)

    def test_partial_period(self):
        # seules les nuits du 11 et du 12 tombent dans la période
        data = self._data('2091-01-11', '2091-01-20')
        self.assertEqual(data['period']['nights'], 4)
        # l'arrivée (10/01) est hors période : la réservation n'est pas comptée
        self.assertEqual(data['month_reservations'], 0)

    def test_checkout_day_not_a_night(self):
        self.assertEqual(self._data('2091-01-13', '2091-01-13')['period']['nights'], 0)

    def test_reversed_dates_and_default(self):
        data = self._data('2091-01-31', '2091-01-01')
        self.assertEqual(data['period']['start'], '2091-01-01')
        self.assertEqual(data['period']['nights'], 6)
        default = self.env['hotel.reservation'].get_dashboard_data()
        today = str(fields.Date.context_today(self.env['hotel.reservation']))
        self.assertEqual((default['period']['start'], default['period']['end']), (today, today))
