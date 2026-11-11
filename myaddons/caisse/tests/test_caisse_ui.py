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
                url, "console.log('test successful')",
                ready="!!document.querySelector('.o_kanban_renderer .o_kanban_record')",
                login='admin')
