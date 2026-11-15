from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestCaisseUi(HttpCase):

    def setUp(self):
        super().setUp()
        self.env.ref('base.user_admin').password = 'admin'

    def test_caisse_views_render(self):
        session = self.env['caisse.session']._get_open_session()             or self.env['caisse.session'].create({'opening_balance': 1000})
        self.env['caisse.move'].create({
            'session_id': session.id, 'move_type': 'expense', 'amount': 200, 'reason': 'Test'})
        for url in ('/odoo/action-caisse.action_caisse_session',
                    '/odoo/action-caisse.action_caisse_move?view_type=kanban'):
            self.browser_js(
                url, "setTimeout(() => { const n = document.querySelectorAll('.o_caisse_card, .o_caisse_move').length; if (n) { console.log('test successful'); } else { console.error('Aucune carte kanban affichée'); } }, 5000)",
                login='admin')

    def _session_with_ops(self):
        session = self.env['caisse.session']._get_open_session() \
            or self.env['caisse.session'].create({'opening_balance': 1000})
        self.env['caisse.move'].create({
            'session_id': session.id, 'move_type': 'expense', 'amount': 150,
            'reason': 'Dépense tableau de bord'})
        return session

    def test_dashboard_renders(self):
        """Tableau de bord : caisse ouverte, formule et opérations affichées."""
        self._session_with_ops()
        self.browser_js(
            '/odoo/action-caisse.action_caisse_dashboard',
            """
            const txt = document.querySelector('.o_caisse_dashboard').innerText.toLowerCase();
            if (!txt.includes('doit être en caisse') || !txt.includes('dépense tableau de bord')) {
                console.error('Tableau de bord incomplet : ' + txt.slice(0, 400));
            } else {
                console.log('test successful');
            }
            """,
            ready="!!document.querySelector('.o_caisse_dashboard .o_cd_formula')",
            login='admin')

    def test_dashboard_quick_expense(self):
        """Bouton « Dépense » du tableau de bord : la fenêtre de saisie s'ouvre."""
        self._session_with_ops()
        self.browser_js(
            '/odoo/action-caisse.action_caisse_dashboard',
            """
            document.querySelector('.o_cd_actions .btn-danger').click();
            const t = setInterval(() => {
                if (document.querySelector(".modal .o_field_widget[name='amount']")) {
                    clearInterval(t);
                    console.log('test successful');
                }
            }, 200);
            """,
            ready="!!document.querySelector('.o_cd_actions .btn-danger')",
            login='admin')

    def test_session_form_and_journal_render(self):
        session = self._session_with_ops()
        self.browser_js(
            '/odoo/action-caisse.action_caisse_session/%s' % session.id,
            "console.log('test successful')",
            ready="!!document.querySelector('.o_caisse_summary .o_caisse_sum_theo')"
                  " && !!document.querySelector(\"button[name='action_new_expense']\")",
            login='admin')
        self.browser_js(
            '/odoo/action-caisse.action_caisse_journal',
            "console.log('test successful')",
            ready="[...document.querySelectorAll('.o_list_view .o_data_row')]"
                  ".some(r => r.innerText.includes('Dépense tableau de bord'))",
            login='admin')
