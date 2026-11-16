from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged


def _user(env, login, group):
    return env['res.users'].with_context(no_reset_password=True).create({
        'name': login, 'login': login, 'group_ids': [(6, 0, [env.ref(group).id])]})


def _close_open_sessions(env):
    for session in env['caisse.session'].search([('state', '=', 'open')]):
        session.action_close()


@tagged('post_install', '-at_install')
class TestCaisseMoves(TransactionCase):
    """Menus Entrées / Dépenses / Sorties, saisie par un caissier (non responsable)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))
        _close_open_sessions(cls.env)
        cls.cashier = _user(cls.env, 'caissier_moves', 'caisse.group_caisse_user')
        cls.Move = cls.env['caisse.move'].with_user(cls.cashier)
        cls.beneficiary = cls.env['res.partner'].create({'name': 'Employé avance'})

    def test_cashier_moves_and_balance(self):
        session = self.env['caisse.session'].with_user(self.cashier).create(
            {'opening_balance': 1000})
        before = session.theoretical_balance
        moves = self.Move.create([
            {'move_type': 'in', 'amount': 500, 'reason': 'Fond de départ'},
            {'move_type': 'out', 'amount': 80, 'reason': 'Avance personnel',
             'partner_id': self.beneficiary.id},
            {'move_type': 'transfer', 'amount': 200, 'reason': 'Dépôt banque',
             'destination': 'Banque'},
        ])
        # La caisse ouverte est proposée par défaut
        self.assertEqual(moves.session_id, session)
        self.assertEqual(moves.mapped('signed_amount'), [500, -80, -200])
        self.assertEqual(session.theoretical_balance, before + 500 - 80 - 200)
        lines = self.env['caisse.journal'].search([('session_id', '=', session.id)])
        self.assertEqual(
            {(l.kind, l.category) for l in lines},
            {('float', 'in'), ('in', 'in'), ('out', 'out'), ('transfer', 'out')})
        # Correction et suppression possibles tant que la caisse est ouverte
        moves[1].amount = 100
        self.assertEqual(session.theoretical_balance, before + 500 - 100 - 200)
        moves[2].unlink()
        self.assertEqual(session.theoretical_balance, before + 500 - 100)

        session.closing_balance = session.theoretical_balance
        session.action_close()
        with self.assertRaises(ValidationError):
            moves[0].amount = 1
        with self.assertRaises(UserError):
            moves[0].unlink()

    def test_controls(self):
        session = self.env['caisse.session'].create({'opening_balance': 0})
        with self.assertRaises(ValidationError):
            self.Move.create({'move_type': 'in', 'amount': 0, 'reason': 'x'})
        with self.assertRaises(ValidationError):
            self.Move.create({'move_type': 'in', 'amount': -10, 'reason': 'x'})
        # Sortie : il faut dire à qui l'argent a été remis
        with self.assertRaisesRegex(ValidationError, 'Bénéficiaire'):
            self.Move.create({'move_type': 'out', 'amount': 10, 'reason': 'x'})
        # Le type ne change jamais après la création
        move = self.Move.create({'move_type': 'in', 'amount': 10, 'reason': 'x'})
        with self.assertRaises(UserError):
            move.move_type = 'transfer'
        session.action_close()
        # Aucune caisse ouverte : la saisie est refusée
        with self.assertRaisesRegex(UserError, "Aucune caisse n'est ouverte"):
            self.Move.create({'move_type': 'in', 'amount': 10, 'reason': 'x'})
        with self.assertRaisesRegex(UserError, "Aucune caisse n'est ouverte"):
            self.env['caisse.journal'].action_caisse_new_in()

    def test_menus(self):
        root = self.env.ref('caisse.menu_caisse_root')
        names = root.child_id.mapped('name')
        for name in ('Entrées', 'Dépenses', 'Sorties'):
            self.assertIn(name, names)
        self.assertNotIn('Entrées et dépenses', names)
        expenses = self.env.ref('caisse.menu_caisse_depenses')
        self.assertEqual(expenses.child_id.mapped('name'),
                         ['Toutes les dépenses', 'Notes de frais', 'Achats'])
        # Boutons « Nouveau » des menus
        session = self.env['caisse.session'].create({'opening_balance': 0})
        Journal = self.env['caisse.journal']
        self.assertEqual(Journal.action_caisse_new_in()['context']['default_move_type'], 'in')
        self.assertEqual(Journal.action_caisse_new_out()['context']['default_move_type'], 'out')
        self.assertEqual(
            Journal.action_caisse_new_transfer()['context']['default_move_type'], 'transfer')
        # Notes de frais et achats : créés dans leurs applications, pas en caisse
        for method in ('action_caisse_new_expense_note', 'action_caisse_new_purchase'):
            self.assertFalse(hasattr(Journal, method))
        for method in ('action_new_expense', 'action_new_expense_note', 'action_new_purchase'):
            self.assertFalse(hasattr(session, method))
        session.action_close()

    def test_access(self):
        other = _user(self.env, 'sans_caisse_moves', 'base.group_user')
        with self.assertRaises(AccessError):
            self.env['caisse.move'].with_user(other).search([])


@tagged('post_install', '-at_install')
class TestCaisseExpenses(TransactionCase):
    """Dépenses = notes de frais + achats ; chaque paiement validé en espèces
    sort de la caisse et apparaît dans le menu Dépenses."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))
        _close_open_sessions(cls.env)
        cls.product = cls.env['product.product'].search(
            [('can_be_expensed', '=', True)], limit=1)
        cls.cash = cls.env['account.journal'].search(
            [('type', '=', 'cash'), ('company_id', '=', cls.env.company.id)], limit=1)

    def _new_expense(self, amount, name='Taxi courses'):
        """Note de frais saisie dans l'application Notes de frais : payée par
        la société, en espèces (journal Espèces)."""
        return self.env['hr.expense'].create({
            'name': name, 'product_id': self.product.id, 'total_amount_currency': amount,
            'employee_id': self.env.user.employee_id.id,
            'payment_mode': 'company_account',
            'payment_method_line_id': self.cash.outbound_payment_method_line_ids[:1].id})

    def _expense_note(self, amount, name='Taxi courses'):
        expense = self._new_expense(amount, name)
        expense.action_submit()  # validation -> paiement en espèces
        return expense

    def _vendor_bill_paid_cash(self, amount):
        supplier = self.env['res.partner'].create({'name': 'Fournisseur dépenses'})
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': supplier.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {'name': 'Draps', 'quantity': 1,
                                         'price_unit': amount, 'tax_ids': [(6, 0, [])]})],
        })
        bill.action_post()
        action = bill.action_register_payment()
        self.env['account.payment.register'].with_context(**action['context']).create({
            'journal_id': self.cash.id}).action_create_payments()
        return bill

    def test_expense_note_paid_by_caisse(self):
        session = self.env['caisse.session'].create({'opening_balance': 5000})
        expense = self._expense_note(700)
        payment = expense.account_move_id.origin_payment_id
        self.assertEqual(payment.state, 'paid')
        self.assertEqual(payment.caisse_session_id, session)
        self.assertEqual(payment.caisse_kind, 'expense_note')
        self.assertEqual(session.total_expense_notes, 700)
        self.assertEqual(session.total_supplier_payments, 0)
        self.assertEqual(session.total_spent, 700)
        self.assertEqual(session.theoretical_balance, 5000 - 700)
        line = self.env['caisse.journal'].search([('payment_id', '=', payment.id)])
        self.assertEqual((line.kind, line.category, line.amount_out), ('expense_note', 'expense', 700))
        # Depuis le menu Dépenses, la ligne ouvre la note de frais
        self.assertEqual(line.action_open_source()['res_model'], 'hr.expense')
        self.assertEqual(session.expense_note_payment_ids, payment)
        html = self.env['ir.actions.report']._render_qweb_html(
            'caisse.action_report_caisse_session', session.ids)[0]
        self.assertIn(b'Note de frais', html)

    def test_employee_expense_reimbursed_cash(self):
        """Note de frais payée par l'employé, puis remboursée en espèces
        (bouton « Payer » du reçu) : c'est une note de frais, pas un achat."""
        session = self.env['caisse.session'].create({'opening_balance': 4000})
        expense = self.env['hr.expense'].create({
            'name': 'Taxi employé', 'product_id': self.product.id,
            'total_amount_currency': 650, 'employee_id': self.env.user.employee_id.id,
            'payment_mode': 'own_account'})
        expense.action_submit()
        receipt = expense.account_move_id
        if receipt.state == 'draft':
            receipt.action_post()
        action = receipt.action_register_payment()
        self.env['account.payment.register'].with_context(**action['context']).create({
            'journal_id': self.cash.id}).action_create_payments()
        payment = session.payment_ids
        self.assertEqual(len(payment), 1)
        self.assertEqual(payment.caisse_kind, 'expense_note')
        self.assertEqual(session.total_expense_notes, 650)
        self.assertEqual(session.total_supplier_payments, 0)
        line = self.env['caisse.journal'].search([('payment_id', '=', payment.id)])
        self.assertEqual((line.kind, line.category), ('expense_note', 'expense'))
        self.assertEqual(line.action_open_source()['res_model'], 'hr.expense')

    def test_expense_note_requires_open_session(self):
        expense = self._new_expense(50, 'Sans caisse')
        with self.assertRaisesRegex(UserError, "Aucune caisse n'est ouverte"):
            expense.action_submit()

    def test_purchase_and_categories(self):
        session = self.env['caisse.session'].create({'opening_balance': 3000})
        self._expense_note(200)
        bill = self._vendor_bill_paid_cash(900)
        self.assertIn(bill.payment_state, ('paid', 'in_payment'))
        self.env['caisse.move'].create({'move_type': 'in', 'amount': 1000,
                                        'reason': 'Fond avant les réservations'})
        self.env['caisse.move'].create({
            'move_type': 'out', 'amount': 100, 'reason': 'Avance',
            'partner_id': self.env.user.partner_id.id})
        Journal = self.env['caisse.journal']
        domain = [('session_id', '=', session.id)]
        expenses = Journal.search(domain + eval(self.env.ref('caisse.action_caisse_depenses').domain))
        self.assertEqual(sorted(expenses.mapped('kind')), ['expense_note', 'purchase'])
        notes = Journal.search(domain + eval(self.env.ref('caisse.action_caisse_notes_frais').domain))
        self.assertEqual(notes.mapped('kind'), ['expense_note'])
        purchases = Journal.search(domain + eval(self.env.ref('caisse.action_caisse_achats').domain))
        self.assertEqual(purchases.mapped('amount_out'), [900])
        ins = Journal.search(domain + eval(self.env.ref('caisse.action_caisse_entrees').domain))
        self.assertEqual(ins.mapped('kind'), ['in'])
        outs = Journal.search(domain + eval(self.env.ref('caisse.action_caisse_sorties').domain))
        self.assertEqual(outs.mapped('kind'), ['out'])
        self.assertEqual(session.total_spent, 200 + 900 + 100)
        self.assertEqual(session.theoretical_balance, 3000 + 1000 - 200 - 900 - 100)
        data = self.env['caisse.session'].get_dashboard_data()
        self.assertEqual(data['current']['expense_notes'], 200)
        self.assertEqual(data['current']['supplier_payments'], 900)
        self.assertGreaterEqual(data['month']['expense'], 200)
        self.assertGreaterEqual(data['month']['purchase'], 900)


@tagged('post_install', '-at_install')
class TestCaisseMovesUi(HttpCase):

    def setUp(self):
        super().setUp()
        self.env.ref('base.user_admin').password = 'admin'
        self.caisse = self.env['caisse.session']._get_open_session() \
            or self.env['caisse.session'].create({'opening_balance': 1000})

    def test_menu_views_render(self):
        self.env['caisse.move'].create({
            'session_id': self.caisse.id, 'move_type': 'in', 'amount': 90,
            'reason': 'Vue menu'})
        for action in ('action_caisse_entrees', 'action_caisse_depenses',
                       'action_caisse_notes_frais', 'action_caisse_achats',
                       'action_caisse_sorties'):
            self.browser_js(
                '/odoo/action-caisse.%s' % action,
                "console.log('test successful')",
                ready="!!document.querySelector('.o_list_view .o_list_button_add, "
                      ".o_list_view .o_control_panel button.btn-primary, .o_list_view')",
                login='admin')

    def _create_from_menu(self, action, button, reason, extra_js=''):
        """Menu -> bouton « Nouvelle … » -> fenêtre de saisie -> enregistrer.
        Le champ Type n'est pas affiché : le type vient du bouton."""
        self.browser_js(
            '/odoo/action-caisse.%s' % action,
            """
            const set = (name, value) => {
                const input = document.querySelector(`.modal .o_field_widget[name='${name}'] input`);
                input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            };
            const btn = [...document.querySelectorAll('.o_control_panel button, .o_list_view button')]
                .find((b) => b.textContent.trim() === '%(button)s');
            if (!btn) {
                console.error('Bouton %(button)s absent');
            } else {
                btn.click();
                const wait = setInterval(() => {
                    if (!document.querySelector(".modal .o_field_widget[name='amount'] input")) {
                        return;
                    }
                    clearInterval(wait);
                    if (document.querySelector(".modal .o_field_widget[name='move_type']")) {
                        console.error('Le champ Type est affiché');
                        return;
                    }
                    set('amount', '345');
                    set('reason', '%(reason)s');
                    %(extra)s
                    setTimeout(() => {
                        document.querySelector('.modal .o_form_button_save, .modal footer .btn-primary').click();
                        const done = setInterval(() => {
                            if (!document.querySelector('.modal')) {
                                clearInterval(done);
                                console.log('test successful');
                            }
                        }, 300);
                    }, 1500);
                }, 300);
            }
            """ % {'button': button, 'reason': reason, 'extra': extra_js},
            ready="!!document.querySelector('.o_list_view')",
            login='admin', timeout=90)
        return self.env['caisse.move'].search([('reason', '=', reason)])

    def test_menu_new_entry(self):
        move = self._create_from_menu('action_caisse_entrees', 'Nouvelle entrée',
                                      'Fond avant reservations')
        self.assertEqual((move.move_type, move.amount, move.session_id),
                         ('in', 345, self.caisse))

    def test_menu_new_transfer(self):
        move = self._create_from_menu('action_caisse_sorties', 'Nouveau transfert',
                                      'Depot banque')
        self.assertEqual((move.move_type, move.amount), ('transfer', 345))
