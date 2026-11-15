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
        # Paiements espèces déjà présents dans la base sur la période (données réelles)
        cash_before = dict(session.payments_by_mode())['Espèces']
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
        self.assertEqual(dict(session.payments_by_mode())['Espèces'] - cash_before, 4000)
        session.closing_balance = 4750
        session.action_close()
        self.assertEqual(session.difference, -50)
        with self.assertRaises(ValidationError):
            self.env['caisse.move'].create({
                'session_id': session.id, 'move_type': 'in', 'amount': 1, 'reason': 'x'})
        html = self.env['ir.actions.report']._render_qweb_html(
            'caisse.action_report_caisse_session', session.ids)[0]
        self.assertIn(session.name.encode(), html)

    def _invoice_pay_cash(self):
        """Bouton « Payer » de la facture du séjour, en espèces."""
        invoice = self.resa._hotel_create_invoice()
        invoice.action_post()
        cash_line = self.env['account.journal']._hotel_get_payment_method_line(
            'cash', invoice.company_id)
        action = invoice.action_register_payment()
        wizard = self.env['account.payment.register'].with_context(**action['context']).create({
            'journal_id': cash_line.journal_id.id,
            'payment_method_line_id': cash_line.id,
        })
        wizard.action_create_payments()
        return invoice

    def test_invoice_pay_cash_goes_to_caisse(self):
        session = self.env['caisse.session'].create({'opening_balance': 0})
        invoice = self._invoice_pay_cash()
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))
        payment = session.payment_ids
        self.assertEqual(len(payment), 1, "Le paiement « Payer » doit être dans la caisse")
        self.assertEqual(payment.hotel_reservation_id, self.resa)
        self.assertEqual(session.total_cash_payments, invoice.amount_total)

    def test_invoice_pay_cash_requires_open_session(self):
        with self.assertRaises(UserError):
            self._invoice_pay_cash()

    def test_journal_and_dashboard(self):
        """Journal unifié (paiements + mouvements) et données du tableau de bord."""
        session = self.env['caisse.session'].create({'opening_balance': 1000})
        self._pay('cash', 3000)
        self.env['caisse.move'].create({
            'session_id': session.id, 'move_type': 'expense', 'amount': 400,
            'reason': 'Ampoules'})
        lines = self.env['caisse.journal'].search([('session_id', '=', session.id)])
        self.assertEqual(sorted(lines.mapped('kind')), ['expense', 'payment'])
        self.assertEqual(sum(lines.mapped('amount_in')), 3000)
        self.assertEqual(sum(lines.mapped('amount_out')), 400)
        self.assertEqual(sum(lines.mapped('amount')), session.theoretical_balance - 1000)
        self.assertEqual(session.journal_count, 2)
        # Ouverture de l'opération d'origine depuis le journal
        expense_line = lines.filtered(lambda l: l.kind == 'expense')
        self.assertEqual(expense_line.action_open_source()['res_model'], 'caisse.move')

        data = self.env['caisse.session'].get_dashboard_data()
        self.assertEqual(data['current']['id'], session.id)
        self.assertEqual(data['current']['theoretical'], 3600)
        self.assertEqual(data['current']['spent'], 400)
        self.assertGreaterEqual(data['month']['expense'], 400)
        self.assertGreaterEqual(data['month']['missing_proof'], 1)  # dépense sans justificatif
        self.assertEqual(len(data['days']), 7)

        # Saisie rapide depuis la caisse : type et caisse pré-remplis
        action = session.action_new_out()
        self.assertEqual(action['context']['default_move_type'], 'out')
        self.assertEqual(action['context']['default_session_id'], session.id)
        session.closing_balance = 3600
        session.action_close()
        with self.assertRaises(UserError):
            session.action_new_in()
        data = self.env['caisse.session'].get_dashboard_data()
        self.assertFalse(data['current'])
        self.assertEqual(data['last_closed'][0]['id'], session.id)
        self.assertEqual(data['last_closed'][0]['difference'], 0)

    def _vendor_bill_pay_cash(self, amount=700):
        """Facture fournisseur payée en espèces avec le bouton « Payer »."""
        supplier = self.env['res.partner'].create({'name': 'Fournisseur caisse'})
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': supplier.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'name': 'Produits ménage', 'quantity': 1, 'price_unit': amount,
                'tax_ids': [(6, 0, [])]})],
        })
        bill.action_post()
        cash_journal = self.env['account.journal'].search([
            ('type', '=', 'cash'), ('company_id', '=', bill.company_id.id)], limit=1)
        action = bill.action_register_payment()
        wizard = self.env['account.payment.register'].with_context(**action['context']).create({
            'journal_id': cash_journal.id,
        })
        wizard.action_create_payments()
        return bill

    def test_supplier_cash_payment_goes_to_caisse(self):
        session = self.env['caisse.session'].create({'opening_balance': 1000})
        self._pay('cash', 3000)
        bill = self._vendor_bill_pay_cash(700)
        self.assertIn(bill.payment_state, ('paid', 'in_payment'))
        self.assertEqual(len(session.supplier_payment_ids), 1)
        self.assertEqual(len(session.customer_payment_ids), 1)
        self.assertEqual(session.total_cash_payments, 3000)
        self.assertEqual(session.total_supplier_payments, 700)
        self.assertEqual(session.total_spent, 700)
        self.assertEqual(session.theoretical_balance, 1000 + 3000 - 700)
        # Les achats ne sont pas des recettes : absents des paiements par mode
        self.assertNotIn(session.supplier_payment_ids, session.period_payment_ids)
        line = self.env['caisse.journal'].search([
            ('session_id', '=', session.id), ('kind', '=', 'purchase')])
        self.assertEqual(line.amount_out, 700)
        self.assertEqual(line.amount, -700)
        data = self.env['caisse.session'].get_dashboard_data()
        self.assertEqual(data['current']['supplier_payments'], 700)
        self.assertGreaterEqual(data['month']['purchase'], 700)
        html = self.env['ir.actions.report']._render_qweb_html(
            'caisse.action_report_caisse_session', session.ids)[0]
        self.assertIn(b'Achat fournisseur', html)

    def test_supplier_cash_payment_requires_open_session(self):
        with self.assertRaises(UserError):
            self._vendor_bill_pay_cash(500)
