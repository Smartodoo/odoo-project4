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

    def test_bed_kanban_renders(self):
        self.browser_js(
            '/odoo/action-hotel_management.action_hotel_bed',
            "console.log('test successful')",
            ready="!!document.querySelector('.o_hotel_kanban .o_hotel_kcard')",
            login='admin')

    def test_bed_form_statusbar(self):
        bed = self.env['hotel.bed'].search([], limit=1)
        if not bed:
            self.skipTest("Aucun lit dans la base")
        self.browser_js(
            '/odoo/action-hotel_management.action_hotel_bed/%s' % bed.id,
            "console.log('test successful')",
            ready="!!document.querySelector('.o_form_view .o_hotel_status .o_arrow_button_current')",
            login='admin')

    def test_bed_statusbar_current_is_colored(self):
        """L'état actuel du lit est bien coloré (pas le gris/blanc natif)."""
        bed = self.env['hotel.bed'].search([], limit=1)
        if not bed:
            self.skipTest("Aucun lit dans la base")
        self.browser_js(
            '/odoo/action-hotel_management.action_hotel_bed/%s' % bed.id,
            """
            const btn = document.querySelector('.o_hotel_statusbar .o_arrow_button_current');
            const bg = getComputedStyle(btn).backgroundColor;
            const color = getComputedStyle(btn).color;
            if (['rgba(0, 0, 0, 0)', 'rgb(255, 255, 255)'].includes(bg) || color !== 'rgb(255, 255, 255)') {
                console.error('Etat actuel non coloré : fond ' + bg + ', texte ' + color);
            } else {
                console.log('test successful');
            }
            """,
            ready="!!document.querySelector('.o_hotel_statusbar .o_arrow_button_current')",
            login='admin')

    def test_partner_rates_editable(self):
        """Configuration > Tarifs clients : la liste s'affiche et le tarif
        spécial saisi est celui utilisé pour le prix de la nuit."""
        partner = self.env['res.partner'].create({
            'name': 'Client Tarif Test', 'hotel_special_room_price': 2500})
        self.browser_js(
            '/odoo/action-hotel_management.action_hotel_partner_rates',
            "console.log('test successful')",
            ready="[...document.querySelectorAll('.o_list_view .o_data_row')]"
                  ".some(r => r.innerText.includes('Client Tarif Test'))",
            login='admin')
        room = self.env['hotel.room'].search([], limit=1)
        if room:
            self.assertEqual(room._get_night_price(False, 'room', partner), 2500)

    def test_encaisser_dialog_opens(self):
        """La fenêtre « Encaisser » s'ouvre (régression : le thème modifiait
        les props du formulaire en dialogue, ce qui plantait sous Odoo 20)."""
        resa = self.env['hotel.reservation'].search(
            [('state', 'not in', ('cancel', 'draft'))], limit=50).filtered(
            lambda r: r.amount_due > 0 and r.partner_id)[:1]
        if not resa:
            self.skipTest("Aucune réservation avec un reste à payer")
        # Fiche client complète (champs obligatoires du client principal)
        partner = resa.partner_id
        partner.write({k: v for k, v in {
            'hotel_last_name': partner.hotel_last_name or 'Test',
            'hotel_first_name': partner.hotel_first_name or 'Test',
            'hotel_birthdate': partner.hotel_birthdate or '1990-01-01',
            'phone': partner.phone or '0550000000',
            'street': partner.street or '1 rue Test',
            'hotel_id_type': partner.hotel_id_type or 'cni',
            'hotel_id_number': partner.hotel_id_number or 'ID-TEST',
        }.items()})
        self.browser_js(
            '/odoo/action-hotel_management.action_hotel_reservation/%s' % resa.id,
            """
            document.querySelector("button[name='action_register_hotel_payment']").click();
            const t = setInterval(() => {
                if (document.querySelector(".modal button[name='action_confirm']")) {
                    clearInterval(t);
                    console.log('test successful');
                }
            }, 200);
            """,
            ready="!!document.querySelector(\"button[name='action_register_hotel_payment']\")",
            login='admin')

    def test_website_booking(self):
        """Réservation en ligne : prix calculé, confirmation protégée par jeton."""
        from datetime import timedelta
        import re
        from odoo import fields
        rtype = self.env['hotel.room.type'].create({'name': 'Web', 'room_price': 3000})
        room = self.env['hotel.room'].create({
            'name': 'WEB-1', 'capacity': 2, 'website_published': True})
        ci = fields.Date.today() + timedelta(days=700)
        co = ci + timedelta(days=2)
        page = self.url_open('/hotel/book?type_id=%s&checkin=%s&checkout=%s&guests=1&booking_type=room'
                             % (rtype.id, ci, co))
        self.assertEqual(page.status_code, 200)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        res = self.url_open('/hotel/booking/submit', data={
            'csrf_token': token, 'room_id': room.id, 'type_id': rtype.id, 'checkin': str(ci), 'checkout': str(co),
            'guests': 1, 'booking_type': 'room', 'last_name': 'Client', 'first_name': 'Web', 'birthdate': '1990-01-01', 'street': '1 rue Test',
            'email': 'client.web@example.com', 'phone': '0550000000'}, allow_redirects=False)
        self.assertIn(res.status_code, (302, 303))
        self.assertIn('access_token=', res.headers['Location'])
        resa = self.env['hotel.reservation'].search([('line_ids.room_id', '=', room.id)])
        self.assertEqual(resa.source, 'website')
        # Réservation en ligne : brouillon, confirmée ensuite par l'hôtel
        self.assertEqual(resa.state, 'draft')
        self.assertEqual(resa.amount_total, 6000)
        # Sans jeton : pas d'accès à la confirmation
        blocked = self.url_open('/hotel/booking/confirmation/%s' % resa.id, allow_redirects=False)
        self.assertIn(blocked.status_code, (302, 303))
        ok = self.url_open(res.headers['Location'])
        self.assertEqual(ok.status_code, 200)
        self.assertIn(resa.name, ok.text)

    def _web_book(self, room, ci, co, last, first, email, login=None,
                  birthdate='1990-05-17', street='5 rue des Pins'):
        import re
        if login:
            self.authenticate(login, login)
        page = self.url_open('/hotel/book?type_id=%s&checkin=%s&checkout=%s&guests=1&booking_type=room'
                             % (self._rtype.id, ci, co))
        self.assertEqual(page.status_code, 200)
        token = re.search(r'csrf_token["\']?\s*(?:value=|:)\s*["\']([^"\']+)', page.text).group(1)
        res = self.url_open('/hotel/booking/submit', data={
            'csrf_token': token, 'room_id': room.id, 'type_id': self._rtype.id,
            'checkin': str(ci), 'checkout': str(co),
            'guests': 1, 'booking_type': 'room', 'last_name': last, 'first_name': first,
            'birthdate': birthdate, 'street': street, 'city': 'Oran', 'phone': '0551000000',
            'email': email}, allow_redirects=False)
        self.assertIn(res.status_code, (302, 303))
        return self.env['hotel.reservation'].search(
            [('line_ids.room_id', '=', room.id), ('checkin', '=', ci)])

    def test_website_booking_new_customer(self):
        """Le client d'une réservation en ligne est la personne saisie : jamais
        l'admin connecté, ni un contact interne qui partage l'e-mail ; un même
        nom + prénom + e-mail reprend le contact existant."""
        from datetime import timedelta
        from odoo import fields
        admin = self.env.ref('base.user_admin')
        admin.partner_id.email = 'partage.web@example.com'
        rtype = self._rtype = self.env['hotel.room.type'].create({'name': 'WebN', 'room_price': 1000})
        room = self.env['hotel.room'].create({
            'name': 'WEB-N', 'capacity': 2, 'website_published': True})
        d = fields.Date.today() + timedelta(days=800)
        # Visiteur anonyme avec l'e-mail de l'admin -> nouveau contact
        r1 = self._web_book(room, d, d + timedelta(days=1), 'Nouveau', 'Client',
                            'partage.web@example.com')
        self.assertNotEqual(r1.partner_id, admin.partner_id)
        self.assertEqual(r1.partner_id.hotel_last_name, 'Nouveau')
        self.assertEqual(r1.partner_id.hotel_first_name, 'Client')
        self.assertEqual(r1.partner_id.name, 'Nouveau Client')
        self.assertEqual(str(r1.partner_id.hotel_birthdate), '1990-05-17')
        self.assertEqual(r1.partner_id.street, '5 rue des Pins')
        self.assertEqual(r1.partner_id.city, 'Oran')
        self.assertEqual(r1.partner_street, '5 rue des Pins')
        self.assertEqual(r1.state, 'draft')
        # Même nom/prénom/e-mail (casse différente) -> même contact
        r2 = self._web_book(room, d + timedelta(days=2), d + timedelta(days=3),
                            'NOUVEAU', 'client', 'Partage.Web@example.com')
        self.assertEqual(r2.partner_id, r1.partner_id)
        # Même e-mail mais autre prénom -> autre contact
        r3 = self._web_book(room, d + timedelta(days=4), d + timedelta(days=5),
                            'Nouveau', 'Autre', 'partage.web@example.com')
        self.assertNotEqual(r3.partner_id, r1.partner_id)
        # Admin connecté qui réserve pour un client -> le client, pas l'admin
        r4 = self._web_book(room, d + timedelta(days=6), d + timedelta(days=7),
                            'Client', 'Guichet', 'guichet.web@example.com', login='admin')
        self.assertNotEqual(r4.partner_id, admin.partner_id)
        self.assertEqual(r4.partner_id.name, 'Client Guichet')

    def test_website_booking_identity_checks(self):
        """Date de naissance et adresse obligatoires ; client mineur refusé."""
        from datetime import timedelta
        from odoo import fields
        rtype = self.env['hotel.room.type'].create({'name': 'WebM', 'room_price': 1000})
        room = self.env['hotel.room'].create({
            'name': 'WEB-M', 'capacity': 2, 'website_published': True})
        d = fields.Date.today() + timedelta(days=900)
        minor = str(fields.Date.today() - timedelta(days=365 * 10))
        for kw in ({'birthdate': minor}, {'birthdate': ''}, {'street': ''}, {'phone': ''}):
            import re
            page = self.url_open('/hotel/book?type_id=%s&checkin=%s&checkout=%s&guests=1&booking_type=room'
                                 % (rtype.id, d, d + timedelta(days=1)))
            token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
            data = {'csrf_token': token, 'room_id': room.id, 'type_id': rtype.id, 'checkin': str(d),
                    'checkout': str(d + timedelta(days=1)), 'guests': 1, 'booking_type': 'room',
                    'last_name': 'Mineur', 'first_name': 'Test', 'email': 'mineur@example.com',
                    'birthdate': '1990-01-01', 'street': '1 rue', 'phone': '0552000000'}
            data.update(kw)
            res = self.url_open('/hotel/booking/submit', data=data, allow_redirects=False)
            self.assertEqual(res.status_code, 200, kw)  # formulaire réaffiché avec erreur
            self.assertFalse(self.env['hotel.reservation'].search(
                [('line_ids.room_id', '=', room.id)]), kw)

    def test_cash_and_report_views_render(self):
        for action in ('hotel_management.action_hotel_revenue_report',
                       'hotel_management.action_hotel_reservation'):
            self.browser_js(
                '/odoo/action-%s' % action,
                "console.log('test successful')",
                ready="!!document.querySelector('.o_action_manager .o_view_controller')",
                login='admin')

    def test_kanban_views_render(self):
        """Vues kanban : réservations, ménage, travaux, personnel (cartes affichées)."""
        room = self.env['hotel.room'].search([], limit=1)
        self.env['hotel.housekeeping'].create({'room_id': room.id})
        self.env['hotel.maintenance.request'].create({'name': 'Test kanban', 'room_id': room.id})
        self.env['hotel.staff'].create({'name': 'Agent kanban'})
        for url in ('/odoo/action-hotel_management.action_hotel_housekeeping',
                    '/odoo/action-hotel_management.action_hotel_maintenance',
                    '/odoo/action-hotel_management.action_hotel_staff',
                    '/odoo/action-hotel_management.action_hotel_reservation?view_type=kanban'):
            self.browser_js(url, "setTimeout(() => { const n = document.querySelectorAll('.o_hotel_kanban .o_kanban_record:not(.o_kanban_ghost)').length; if (n) { console.log('test successful'); } else { console.error('Aucune carte kanban affichée'); } }, 5000)", login='admin')
