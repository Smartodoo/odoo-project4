from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCaisseFloat(TransactionCase):
    """Fond de caisse = entrées « Fond de caisse » (bouton Entrée)."""

    def setUp(self):
        super().setUp()
        Session = self.env['caisse.session']
        opened = Session._get_open_session()
        if opened:
            opened.action_close()
        self.session = Session.create({})

    def _in(self, amount, kind, session=None):
        return self.env['caisse.move'].create({
            'session_id': (session or self.session).id, 'move_type': 'in',
            'in_kind': kind, 'amount': amount, 'reason': 'test'})

    def test_float_feeds_opening_not_collected(self):
        s = self.session
        self.assertEqual(s.opening_balance, 0)
        self._in(3000, 'float')
        self.assertEqual(s.opening_balance, 3000)
        self.assertEqual(s.total_in, 0)
        self.assertEqual(s.total_collected, 0)
        self.assertEqual(s.theoretical_balance, 3000)
        self._in(500, 'other')
        self.assertEqual(s.opening_balance, 3000)
        self.assertEqual(s.total_in, 500)
        self.assertEqual(s.theoretical_balance, 3500)
        # complément de monnaie en cours de journée : le fond s'additionne
        extra = self._in(1000, 'float')
        self.assertEqual(s.opening_balance, 4000)
        self.assertEqual(s.theoretical_balance, 4500)
        # correction : suppression de l'entrée -> fond recalculé
        extra.unlink()
        self.assertEqual(s.opening_balance, 3000)

    def test_journal_and_dashboard(self):
        self._in(2000, 'float')
        self._in(700, 'other')
        lines = self.env['caisse.journal'].search([('session_id', '=', self.session.id)])
        self.assertEqual(sorted(lines.mapped('kind')), ['float', 'in'])
        self.assertEqual(set(lines.mapped('category')), {'in'})
        data = self.env['caisse.session'].get_dashboard_data()
        self.assertEqual(data['current']['opening'], 2000)
        self.assertEqual(data['current']['moves_in'], 700)
        self.assertEqual(data['current']['theoretical'], 2700)
        # « Entrées diverses » de la période : le fond n'est pas une recette
        self.assertEqual(data['month']['in'], 700)

    def test_kind_locked(self):
        move = self._in(1000, 'float')
        with self.assertRaises(UserError):
            move.in_kind = 'other'

    def test_opening_balance_readonly_api(self):
        self._in(1000, 'float')
        with self.assertRaises(UserError):
            self.session.opening_balance = 5000

    def test_create_with_opening_balance_creates_float(self):
        self.session.action_close()
        session = self.env['caisse.session'].create({'opening_balance': 1500})
        self.assertEqual(session.opening_balance, 1500)
        self.assertEqual(session.move_ids.mapped('in_kind'), ['float'])

    def test_float_prefilled_with_last_closing(self):
        self._in(2500, 'float')
        self.session.closing_balance = 2400
        self.session.action_close()
        new = self.env['caisse.session'].create({})
        view = 'caisse.view_caisse_move_form_quick'
        with Form(self.env['caisse.move'].with_context(
                default_session_id=new.id, default_move_type='in'), view=view) as f:
            f.in_kind = 'float'
            self.assertEqual(f.amount, 2400)
            self.assertEqual(f.reason, 'Fond de caisse')
        self.assertEqual(new.opening_balance, 2400)
