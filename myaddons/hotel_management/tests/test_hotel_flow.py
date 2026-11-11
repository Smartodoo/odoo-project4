from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHotelFlow(TransactionCase):
    """Parcours du cahier des charges : tarifs, remise, consommations, caisse,
    facturation automatique, remboursement, ménage, statistiques."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))
        cls.today = fields.Date.context_today(cls.env['hotel.reservation'])
        cls.ci = cls.today + timedelta(days=500)
        cls.co = cls.ci + timedelta(days=3)
        cls.rtype = cls.env['hotel.room.type'].create({
            'name': 'Type test', 'list_price': 5000, 'rental_mode': 'room'})
        cls.room = cls.env['hotel.room'].create({
            'name': 'T-01', 'room_type_id': cls.rtype.id, 'capacity': 2,
            'room_price': 5000, 'bed_price': 2000, 'rental_mode': 'room'})
        cls.partner = cls.env['res.partner'].create({
            'name': 'Client test', 'hotel_birthdate': '1990-01-01'})

    def _reservation(self, **vals):
        values = {
            'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
            'line_ids': [(0, 0, {'room_id': self.room.id, 'price_unit': 5000})],
        }
        values.update(vals)
        return self.env['hotel.reservation'].create(values)

    def _pay(self, resa, mode, amount, **ctx):
        wizard = self.env['hotel.reservation.payment.wizard'].with_context(**ctx).create({
            'reservation_id': resa.id, 'payment_mode': mode, 'amount': amount})
        wizard.action_confirm()
        return wizard

    def test_seasonal_and_special_prices(self):
        self.env['hotel.rate.season'].create({
            'name': 'Pic', 'date_start': self.ci, 'date_end': self.ci,
            'room_type_id': self.rtype.id, 'price': 8000, 'bed_price': 3000})
        self.assertEqual(self.room._get_stay_unit_price(self.ci, self.co, 'room'),
                         round((8000 + 5000 * 2) / 3, 2))
        self.assertEqual(self.room._get_night_price(self.ci, 'bed'), 3000)
        self.partner.hotel_special_room_price = 4000
        self.assertEqual(self.room._get_night_price(self.ci, 'room', self.partner), 4000)

    def test_full_stay(self):
        resa = self._reservation(discount_type='amount', discount_value=1000)
        self.env['hotel.reservation.service'].create({
            'reservation_id': resa.id,
            'product_id': self.env.ref('hotel_management.product_hotel_breakfast').id,
            'name': 'Petit-déjeuner', 'quantity': 2, 'price_unit': 300})
        self.assertEqual(resa.amount_gross, 15600)
        self.assertEqual(resa.amount_total, 14600)
        resa.action_confirm()
        resa.action_checkin()

        self._pay(resa, 'card', 4000)
        self.assertEqual(resa.deposit_amount, 4000)

        resa.action_checkout()
        invoice = resa.invoice_ids.filtered(lambda m: m.state == 'posted')
        self.assertEqual(len(invoice), 1, "Facture générée et validée au départ")
        self.assertAlmostEqual(invoice.amount_total, 14600)
        self.assertEqual(len(invoice.invoice_line_ids), 3, "Chambre, consommation, remise")
        self.assertAlmostEqual(invoice.amount_residual, 10600, msg="Acompte déduit")
        self.assertEqual(self.room.housekeeping_status, 'dirty')

        self._pay(resa, 'transfer', resa.amount_due)
        self.assertAlmostEqual(resa.amount_due, 0)
        self._pay(resa, 'transfer', 500, hotel_refund=True)
        self.assertAlmostEqual(resa.amount_paid, 14100)

        self.env.flush_all()
        nights = self.env['hotel.revenue.report'].search([('reservation_id', '=', resa.id)])
        self.assertAlmostEqual(sum(nights.mapped('room_nights')), 3)

    def test_housekeeping_cycle(self):
        task = self.env['hotel.housekeeping'].create({'room_id': self.room.id})
        task.action_start()
        self.assertEqual(self.room.housekeeping_status, 'inprogress')
        task.action_done()
        task.action_inspect()
        self.assertEqual(self.room.housekeeping_status, 'inspected')
        self.assertEqual(self.room.status, 'available')
        task.action_to_repair()
        self.assertEqual(self.room.housekeeping_status, 'to_repair')
        self.assertTrue(task.maintenance_id)
        task.maintenance_id.action_done()
        self.assertEqual(self.room.housekeeping_status, 'dirty')

    def test_services_locked_after_invoice(self):
        resa = self._reservation()
        resa.action_confirm()
        resa.action_checkin()
        resa.action_checkout()
        with self.assertRaises(UserError):
            self.env['hotel.reservation.service'].create({
                'reservation_id': resa.id,
                'product_id': self.env.ref('hotel_management.product_hotel_meal').id,
                'name': 'Repas', 'quantity': 1, 'price_unit': 800})

    def test_planning_data(self):
        resa = self._reservation()
        resa.action_confirm()
        data = self.env['hotel.planning'].get_planning_data(fields.Date.to_string(self.ci), 7)
        row = next(r for r in data['rooms'] if r['id'] == self.room.id)
        self.assertEqual(row['bookings'][0]['start'], 0)
        self.assertEqual(row['bookings'][0]['end'], 3)
        self.assertEqual(data['days'][0]['rooms_busy'] >= 1, True)

    def test_partner_discount_onchange(self):
        self.partner.hotel_discount = 15
        with Form(self.env['hotel.reservation']) as form:
            form.partner_id = self.partner
            form.checkout = self.today + timedelta(days=1)
            self.assertEqual(form.discount_value, 15)
