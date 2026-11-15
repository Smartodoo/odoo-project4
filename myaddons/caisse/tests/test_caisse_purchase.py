from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged


def _purchase_order(env, qty=4, price=250):
    supplier = env['res.partner'].create({'name': 'Fournisseur achat caisse'})
    product = env['product.product'].create({
        'name': 'Boisson test caisse', 'type': 'consu', 'purchase_method': 'purchase',
        'standard_price': price})
    order = env['purchase.order'].create({
        'partner_id': supplier.id,
        'order_line': [(0, 0, {'product_id': product.id, 'product_qty': qty,
                               'price_unit': price, 'tax_ids': [(6, 0, [])]})],
    })
    order.button_confirm()
    return order


@tagged('post_install', '-at_install')
class TestCaissePurchase(TransactionCase):
    """Achat -> « Créer la facture » -> payée en espèces -> caisse (Dépenses > Achats)."""

    def test_create_bill_and_pay_cash(self):
        env = self.env(user=self.env.ref('base.user_admin'))
        open_session = env['caisse.session']._get_open_session()
        if open_session:
            open_session.action_close()
            env.flush_all()
        session = env['caisse.session'].create({'opening_balance': 2000})
        order = _purchase_order(env)
        self.assertEqual(order.invoice_status, 'to invoice')
        view = env['purchase.order'].get_view(view_type='form')['arch']
        self.assertIn('Créer la facture', view)

        action = order.action_create_invoice()   # bouton de la fiche, sans fichier
        bill = order.invoice_ids
        self.assertEqual(len(bill), 1)
        self.assertEqual(action['res_id'], bill.id)
        self.assertEqual(bill.move_type, 'in_invoice')
        self.assertEqual(bill.amount_total, 1000)
        self.assertEqual(order.invoice_status, 'invoiced')

        bill.invoice_date = fields.Date.today()
        bill.action_post()
        cash = env['account.journal'].search([
            ('type', '=', 'cash'), ('company_id', '=', bill.company_id.id)], limit=1)
        pay = bill.action_register_payment()
        env['account.payment.register'].with_context(**pay['context']).create({
            'journal_id': cash.id}).action_create_payments()
        line = env['caisse.journal'].search([
            ('session_id', '=', session.id), ('kind', '=', 'purchase')])
        self.assertEqual(line.amount_out, 1000)
        self.assertEqual(line.category, 'expense')
        self.assertEqual(session.theoretical_balance, 2000 - 1000)
        # Depuis le menu Achats de la caisse, la ligne ouvre la facture
        self.assertEqual(line.action_open_source()['res_id'], bill.id)


@tagged('post_install', '-at_install')
class TestCaissePurchaseUi(HttpCase):

    def test_create_bill_button(self):
        self.env.ref('base.user_admin').password = 'admin'
        order = _purchase_order(self.env)
        self.browser_js(
            '/odoo/action-purchase.purchase_form_action/%s' % order.id,
            """
            const btn = [...document.querySelectorAll('.o_form_statusbar button')]
                .find((b) => b.textContent.trim() === 'Créer la facture');
            if (!btn) {
                console.error('Bouton Créer la facture absent');
            } else {
                btn.click();
                const t = setInterval(() => {
                    if (document.querySelector(".o_form_view .o_field_widget[name='invoice_line_ids']")) {
                        clearInterval(t);
                        console.log('test successful');
                    }
                }, 300);
            }
            """,
            ready="!!document.querySelector('.o_form_view .o_form_statusbar')",
            login='admin', timeout=90)
        self.assertEqual(len(order.invoice_ids), 1)


@tagged('post_install', '-at_install')
class TestCaissePurchasePay(TransactionCase):
    """Achat -> « Encaisser » (facture créée et validée, paiement en espèces)."""

    def setUp(self):
        super().setUp()
        self.env = self.env(user=self.env.ref('base.user_admin'))
        open_session = self.env['caisse.session']._get_open_session()
        if open_session:
            open_session.action_close()
            self.env.flush_all()

    def _pay(self, order, **vals):
        action = order.action_caisse_pay()
        wiz = self.env[action['res_model']].with_context(**action['context']).create(vals)
        wiz.action_confirm()
        return wiz

    def test_encaisser_cash_partial_then_full(self):
        session = self.env['caisse.session'].create({'opening_balance': 2000})
        order = _purchase_order(self.env)
        view = self.env['purchase.order'].get_view(view_type='form')['arch']
        self.assertIn('action_caisse_pay', view)
        self.assertEqual(order.caisse_amount_due, 1000)

        self._pay(order, amount=400)
        bill = order.invoice_ids
        self.assertEqual(bill.state, 'posted')
        self.assertEqual(bill.payment_state, 'partial')
        self.assertEqual(order.caisse_amount_paid, 400)
        self.assertEqual(order.caisse_amount_due, 600)

        wiz = self._pay(order)   # montant proposé = reste à payer
        self.assertEqual(wiz.amount, 600)
        self.assertIn(bill.payment_state, ('paid', 'in_payment'))
        self.assertEqual(order.caisse_amount_due, 0)
        with self.assertRaises(UserError):
            order.action_caisse_pay()

        lines = self.env['caisse.journal'].search([
            ('session_id', '=', session.id), ('kind', '=', 'purchase')])
        self.assertEqual(sum(lines.mapped('amount_out')), 1000)
        self.assertEqual(session.theoretical_balance, 1000)

    def test_encaisser_cash_requires_open_session(self):
        order = _purchase_order(self.env)
        with self.assertRaises(UserError):
            self._pay(order, payment_mode='cash')
        self.assertFalse(order.invoice_ids)

    def test_encaisser_bank_without_session(self):
        order = _purchase_order(self.env)
        self._pay(order, payment_mode='transfer')
        self.assertEqual(order.caisse_amount_due, 0)
        payment = order.invoice_ids.matched_payment_ids
        self.assertTrue(payment)
        self.assertFalse(payment.caisse_session_id)

    def test_amount_above_due_refused(self):
        self.env['caisse.session'].create({'opening_balance': 0})
        order = _purchase_order(self.env)
        with self.assertRaises(UserError):
            self._pay(order, amount=1500)


@tagged('post_install', '-at_install')
class TestCaissePurchasePayUi(HttpCase):

    def test_encaisser_button(self):
        self.env.ref('base.user_admin').password = 'admin'
        Session = self.env['caisse.session']
        if not Session._get_open_session():
            Session.create({'opening_balance': 5000})
        order = _purchase_order(self.env)
        self.browser_js(
            '/odoo/action-purchase.purchase_form_action/%s' % order.id,
            """
            const btn = [...document.querySelectorAll('.o_form_statusbar button')]
                .find((b) => b.textContent.trim() === 'Encaisser');
            if (!btn) {
                console.error('Bouton Encaisser absent');
            } else {
                btn.click();
                let clicked = false;
                const t = setInterval(() => {
                    const modal = document.querySelector('.modal .o_form_view');
                    if (!clicked && modal) {
                        clicked = true;
                        document.querySelector(".modal footer button[name='action_confirm']").click();
                    } else if (clicked && !document.querySelector('.modal')) {
                        clearInterval(t);
                        console.log('test successful');
                    }
                }, 300);
            }
            """,
            ready="!!document.querySelector('.o_form_view .o_form_statusbar')",
            login='admin', timeout=90)
        self.assertEqual(order.caisse_amount_due, 0)
