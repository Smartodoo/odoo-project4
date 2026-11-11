from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCaisse(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))
        for session in cls.env['caisse.session'].search([('state', '=', 'open')]):
            session.action_close()
        rtype = cls.env['hotel.room.type'].create({'name': 'Type caisse', 'list_price': 5000})
        cls.room = cls.env['hotel.room'].create({
            'name': 'C-01', 'room_type_id': rtype.id, 'capacity': 2,
            'room_price': 5000, 'rental_mode': 'room'})
        cls.partner = cls.env['res.partner'].create({
            'name': 'Client caisse', 'hotel_birthdate': '1990-01-01'})
        ci = fields.Date.today() + timedelta(days=600)
        cls.resa = cls.env['hotel.reservation'].create({
            'partner_id': cls.partner.id, 'checkin': ci, 'checkout': ci + timedelta(days=2),
            'line_ids': [(0, 0, {'room_id': cls.room.id, 'price_unit': 5000})]})
        cls.resa.action_confirm()
        cls.resa.action_checkin()

    def _pay(self, mode, amount, **ctx):
        wizard = self.env['hotel.reservation.payment.wizard'].with_context(**ctx).create({
            'reservation_id': self.resa.id, 'payment_mode': mode, 'amount': amount})
        wizard.action_confirm()

    def test_cash_requires_open_session(self):
        with self.assertRaises(UserError):
            self._pay('cash', 1000)
        self._pay('card', 1000)  # les autres modes ne passent pas par la caisse
        self.assertEqual(self.resa.amount_paid, 1000)

    def test_session_cycle(self):
        session = self.env['caisse.session'].create({'opening_balance': 2000})
        with self.assertRaises(Exception):
            self.env['caisse.session'].create({'opening_balance': 0})  # une seule caisse ouverte
        self._pay('cash', 4000)
        self.assertEqual(len(session.payment_ids), 1)
        self.env['caisse.move'].create({
            'session_id': session.id, 'move_type': 'expense', 'amount': 500,
            'reason': 'Produits ménage'})
        self.env['caisse.move'].create({
            'session_id': session.id, 'move_type': 'in', 'amount': 300, 'reason': 'Appoint'})
        self.assertEqual(session.total_collected, 4300)
        self.assertEqual(session.total_spent, 500)
        self.assertEqual(session.theoretical_balance, 5800)
        # Remboursement en espèces : sort de la caisse
        self._pay('cash', 1000, hotel_refund=True)
        self.assertEqual(session.theoretical_balance, 4800)
        self.assertEqual(dict(session.payments_by_mode())['Espèces'], 4000)
        session.closing_balance = 4750
        session.action_close()
        self.assertEqual(session.difference, -50)
        with self.assertRaises(ValidationError):
            self.env['caisse.move'].create({
                'session_id': session.id, 'move_type': 'in', 'amount': 1, 'reason': 'x'})
        html = self.env['ir.actions.report']._render_qweb_html(
            'caisse.action_report_caisse_session', session.ids)[0]
        self.assertIn(session.name.encode(), html)
