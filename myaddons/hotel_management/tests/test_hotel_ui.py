from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestHotelUi(HttpCase):
    """Le planning et le tableau de bord s'affichent sans erreur JavaScript."""

    def setUp(self):
        super().setUp()
        # Mot de passe connu pour la durée du test (transaction annulée ensuite)
        self.env.ref('base.user_admin').password = 'admin'

    def test_planning_renders(self):
        self.browser_js(
            '/odoo/action-hotel_management.action_hotel_planning',
            "console.log('test successful')",
            ready="!!document.querySelector('.o_hotel_planning .o_hp_foot')",
            login='admin')

    def test_dashboard_renders(self):
        self.browser_js(
            '/odoo/action-hotel_management.action_hotel_dashboard',
            "console.log('test successful')",
            ready="!!document.querySelector('.o_hotel_dashboard .o_hotel_blocks')",
            login='admin')

    def test_website_booking(self):
        """Réservation en ligne : prix calculé, confirmation protégée par jeton."""
        from datetime import timedelta
        import re
        from odoo import fields
        rtype = self.env['hotel.room.type'].create({'name': 'Web', 'list_price': 3000})
        room = self.env['hotel.room'].create({
            'name': 'WEB-1', 'room_type_id': rtype.id, 'capacity': 2,
            'room_price': 3000, 'rental_mode': 'room', 'website_published': True})
        ci = fields.Date.today() + timedelta(days=700)
        co = ci + timedelta(days=2)
        page = self.url_open('/hotel/room/%s?checkin=%s&checkout=%s&guests=1' % (room.id, ci, co))
        self.assertEqual(page.status_code, 200)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        res = self.url_open('/hotel/booking/submit', data={
            'csrf_token': token, 'room_id': room.id, 'checkin': str(ci), 'checkout': str(co),
            'guests': 1, 'booking_type': 'room', 'name': 'Client Web',
            'email': 'client.web@example.com', 'phone': '0550000000'}, allow_redirects=False)
        self.assertIn(res.status_code, (302, 303))
        self.assertIn('access_token=', res.headers['Location'])
        resa = self.env['hotel.reservation'].search([('line_ids.room_id', '=', room.id)])
        self.assertEqual(resa.source, 'website')
        self.assertEqual(resa.amount_total, 6000)
        # Sans jeton : pas d'accès à la confirmation
        blocked = self.url_open('/hotel/booking/confirmation/%s' % resa.id, allow_redirects=False)
        self.assertIn(blocked.status_code, (302, 303))
        ok = self.url_open(res.headers['Location'])
        self.assertEqual(ok.status_code, 200)
        self.assertIn(resa.name, ok.text)

    def test_cash_and_report_views_render(self):
        for action in ('hotel_management.action_hotel_revenue_report',
                       'hotel_management.action_hotel_reservation'):
            self.browser_js(
                '/odoo/action-%s' % action,
                "console.log('test successful')",
                ready="!!document.querySelector('.o_action_manager .o_view_controller')",
                login='admin')
