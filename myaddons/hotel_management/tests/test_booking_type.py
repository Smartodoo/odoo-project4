import re
from datetime import timedelta

from odoo import fields
from odoo.tests import Form, HttpCase, TransactionCase, tagged


class BookingTypeCommon:
    """Chambres A (3 lits), B, C et D (2 lits) : toutes se louent entières ou
    au lit ; le prix vient du type de chambre de la réservation."""

    @classmethod
    def _setup_rooms(cls):
        cls.ci = fields.Date.today() + timedelta(days=900)
        cls.co = cls.ci + timedelta(days=2)
        # prix lit 1000 : type le moins cher (choisi par le site)
        cls.rtype = cls.env['hotel.room.type'].create({
            'name': 'Type lits', 'room_price': 400, 'bed_price': 1000})

        cls.floor = cls.env['hotel.floor'].create({'name': 'BT étage'})

        def room(name, beds):
            r = cls.env['hotel.room'].create({
                'name': name, 'capacity': beds, 'floor_id': cls.floor.id,
                'website_published': True})
            return r

        cls.room_a = room('BT-A', 3)
        cls.room_b = room('BT-B', 2)
        cls.room_c = room('BT-C', 2)
        cls.room_d = room('BT-D', 2)
        cls.partner = cls.env['res.partner'].create({
            'hotel_last_name': 'Lits', 'hotel_first_name': 'Test', 'phone': '0550000001', 'street': '1 rue Test', 'hotel_id_type': 'cni', 'hotel_id_number': 'ID0001', 'email': 'lits@example.com', 'hotel_birthdate': '1990-01-01'})

    def _book_room(self, room):
        resa = self.env['hotel.reservation'].create({
            'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
            'booking_type': 'room', 'line_ids': [(0, 0, {'room_id': room.id})]})
        resa.action_confirm()
        return resa

    def _book_bed(self, bed, **vals):
        values = {
            'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
            'booking_type': 'bed', 'line_ids': [(0, 0, {'bed_id': bed.id})]}
        values.update(vals)
        resa = self.env['hotel.reservation'].create(values)
        resa.action_confirm()
        return resa


@tagged('post_install', '-at_install')
class TestBookingType(BookingTypeCommon, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))
        cls._setup_rooms()

    def test_bed_line_deduces_room(self):
        bed = self.room_a.bed_ids[1]
        resa = self._book_bed(bed)
        line = resa.line_ids
        self.assertEqual(line.room_id, self.room_a)
        self.assertEqual(line.bed_ids, bed)
        self.assertEqual(resa.places, 1)

    def test_room_line_takes_all_beds(self):
        resa = self._book_room(self.room_c)
        self.assertEqual(resa.line_ids.bed_ids, self.room_c.bed_ids)
        # Impossible de retirer un lit d'une location par chambre
        resa.line_ids.bed_ids = [(6, 0, self.room_c.bed_ids[:1].ids)]
        self.assertEqual(resa.line_ids.bed_ids, self.room_c.bed_ids)

    def test_proposals(self):
        Resa = self.env['hotel.reservation']
        vals = {'checkin': self.ci, 'checkout': self.co, 'booking_type': 'bed'}
        # 2 personnes : chambres de 2 lits libres (B, C, D), pas A (3 lits)
        new = Resa.new(dict(vals, guest_count=2))
        self.assertTrue(self.room_b.bed_ids <= new.proposed_bed_ids._origin)
        self.assertFalse(self.room_a.bed_ids & new.proposed_bed_ids._origin)
        self.assertTrue(self.room_c.bed_ids <= new.proposed_bed_ids._origin)
        # 3 personnes : A
        new = Resa.new(dict(vals, guest_count=3))
        self.assertTrue(self.room_a.bed_ids <= new.proposed_bed_ids._origin)
        self.assertFalse(self.room_b.bed_ids & new.proposed_bed_ids._origin)

        self._book_bed(self.room_a.bed_ids[0])
        new = Resa.new(dict(vals, guest_count=2))
        # A partiellement réservée, 2 lits libres = 2 personnes : seulement A
        proposed = new.proposed_bed_ids._origin
        self.assertEqual(proposed, self.room_a.bed_ids[1:])
        self.assertFalse(self.room_b.bed_ids & proposed)
        # 1 personne : aucune chambre avec 1 lit libre ; i = 1 -> 2 lits
        # libres : A partielle passe avant B libre
        proposed = Resa.new(dict(vals, guest_count=1)).proposed_bed_ids._origin
        self.assertEqual(proposed, self.room_a.bed_ids[1:])
        self.assertFalse(self.room_b.bed_ids & proposed)

        # Par chambre : seulement les chambres libres en entier (C ; pas D
        # déjà réservée, ni A dont un lit est pris)
        self._book_room(self.room_d)
        new = Resa.new({'checkin': self.ci, 'checkout': self.co, 'booking_type': 'room',
                        'guest_count': 2})
        self.assertIn(self.room_c, new.proposed_room_ids._origin)
        self.assertNotIn(self.room_d, new.proposed_room_ids._origin)
        self.assertNotIn(self.room_a, new.proposed_room_ids._origin)

    def test_group_fills_partial_room_first(self):
        """Une fois la chambre partielle pleine, la chambre où le groupe a
        commencé à prendre des lits devient la chambre proposée."""
        self._book_bed(self.room_a.bed_ids[0])
        form = Form(self.env['hotel.reservation'])
        form.floor_id = self.floor
        form.partner_id = self.partner
        form.checkin = self.ci
        form.checkout = self.co
        form.booking_type = 'bed'
        form.children = len(self.room_a.bed_ids) - 2
        for bed in self.room_a.bed_ids[1:]:
            with form.line_ids.new() as line:
                line.bed_id = bed
                self.assertEqual(line.room_id, self.room_a)
        resa = form.save()
        self.assertEqual(len(resa.line_ids), len(self.room_a.bed_ids) - 1)
        self.assertEqual(resa.line_ids.room_id, self.room_a)
        # A est pleine : plus de chambre partielle -> chambres libres proposées
        self.assertTrue(self.room_b.bed_ids <= resa.proposed_bed_ids)

    def test_switch_type_converts_lines(self):
        resa = self.env['hotel.reservation'].new({
            'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
            'booking_type': 'room', 'line_ids': [(0, 0, {'room_id': self.room_c.id})]})
        resa.booking_type = 'bed'
        resa._onchange_booking_type()
        self.assertEqual(len(resa.line_ids), 2)   # une ligne par lit de C
        self.assertEqual(resa.line_ids.bed_id._origin, self.room_c.bed_ids)
        self.assertEqual(resa.line_ids.room_id._origin, self.room_c)
        resa.booking_type = 'room'
        resa._onchange_booking_type()
        self.assertEqual(len(resa.line_ids), 1)   # regroupées sur la chambre
        self.assertEqual(resa.line_ids.bed_ids._origin, self.room_c.bed_ids)

    def test_same_bed_twice_refused(self):
        bed = self.room_a.bed_ids[0]
        with self.assertRaises(Exception):
            self.env['hotel.reservation'].create({
                'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
                'booking_type': 'bed',
                'line_ids': [(0, 0, {'bed_id': bed.id}), (0, 0, {'bed_id': bed.id})]})


@tagged('post_install', '-at_install')
class TestBookingTypeWebsite(BookingTypeCommon, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_rooms()

    def _rooms_page(self, booking_type, guests=1):
        return self.url_open('/hotel/rooms?checkin=%s&checkout=%s&guests=%s&booking_type=%s'
                             % (self.ci, self.co, guests, booking_type)).text

    def _available_part(self, html):
        return html.split('Non disponibles')[0]

    def test_rooms_page_by_type(self):
        self._book_bed(self.room_a.bed_ids[0])
        self._book_room(self.room_d)
        # Sans type choisi : pas de résultats, le client doit choisir
        default = self.url_open('/hotel/rooms?checkin=%s&checkout=%s&guests=1'
                                % (self.ci, self.co)).text
        self.assertIn('Choisissez le type de location', default)
        self.assertIn('Lit en dortoir', default)
        self.assertNotIn('Chambres disponibles', default)
        self.assertIn('Chambre BT-B', self.url_open('/hotel/rooms').text)
        by_room = self._available_part(self._rooms_page('room'))
        self.assertIn('Chambre BT-C', by_room)
        self.assertNotIn('Chambre BT-D', by_room)   # déjà réservée
        self.assertNotIn('Chambre BT-A', by_room)   # un lit déjà loué
        by_bed = self._available_part(self._rooms_page('bed'))
        # une chambre partagée peut loger le voyageur : les chambres
        # entièrement libres ne sont pas proposées
        self.assertIn('Chambre BT-A', by_bed)
        self.assertNotIn('Chambre BT-B', by_bed)
        self.assertNotIn('Chambre BT-C', by_bed)
        self.assertIn('chambres partagées', by_bed)
        # trop de voyageurs pour les lits libres de A -> A n'est plus proposée
        self.assertNotIn('Chambre BT-A', self._available_part(self._rooms_page('bed', 4)))

    def test_website_only_free_rooms(self):
        """Recherche « chambre entière » : seules les chambres libres sur la
        période sont affichées ; la fiche d'une chambre prise ne permet pas de
        réserver et renvoie vers les chambres libres."""
        self._book_room(self.room_d)
        self.env['hotel.reservation'].create({  # brouillon : bloque aussi
            'partner_id': self.partner.id, 'checkin': self.co - timedelta(days=1),
            'checkout': self.co + timedelta(days=2), 'booking_type': 'room',
            'line_ids': [(0, 0, {'room_id': self.room_c.id})]})
        page = self._rooms_page('room')
        self.assertNotIn('Chambre BT-D', page)
        self.assertNotIn('Chambre BT-C', page)
        self.assertNotIn('Non disponibles', page)
        detail = self.url_open('/hotel/room/%s?checkin=%s&checkout=%s&guests=1&booking_type=room'
                               % (self.room_d.id, self.ci, self.co)).text
        self.assertIn('Voir les chambres libres sur ces dates', detail)
        self.assertRegex(detail, r'<button type="submit"[^>]*disabled')
        # Période libre : réservable
        later = self.co + timedelta(days=10)
        detail = self.url_open('/hotel/room/%s?checkin=%s&checkout=%s&guests=1&booking_type=room'
                               % (self.room_d.id, later, later + timedelta(days=2))).text
        self.assertNotIn('Voir les chambres libres sur ces dates', detail)
        self.assertNotRegex(detail, r'<button type="submit"[^>]*disabled')

    def test_website_only_free_beds(self):
        """Fiche chambre : seuls les lits libres sur toute la période sont
        proposés (une réservation en brouillon bloque aussi le lit)."""
        bed1, bed2, bed3 = self.room_a.bed_ids
        self._book_bed(bed1)  # confirmée, même période
        self.env['hotel.reservation'].create({  # brouillon, chevauche d'une nuit
            'partner_id': self.partner.id, 'checkin': self.co - timedelta(days=1),
            'checkout': self.co + timedelta(days=3), 'booking_type': 'bed',
            'line_ids': [(0, 0, {'bed_id': bed2.id})]})
        url = '/hotel/room/%s?checkin=%s&checkout=%s&guests=1&booking_type=bed'
        page = self.url_open(url % (self.room_a.id, self.ci, self.co)).text
        self.assertNotIn('id="bed_%s"' % bed1.id, page)
        self.assertNotIn('id="bed_%s"' % bed2.id, page)
        self.assertIn('id="bed_%s"' % bed3.id, page)
        # Autre période (après les deux réservations) : tous les lits libres
        later = self.co + timedelta(days=10)
        page = self.url_open(url % (self.room_a.id, later, later + timedelta(days=2))).text
        for bed in (bed1, bed2, bed3):
            self.assertIn('id="bed_%s"' % bed.id, page)
        # Sans dates : aucun lit proposé, on demande les dates
        page = self.url_open('/hotel/room/%s' % self.room_a.id).text
        self.assertNotIn('id="bed_%s"' % bed3.id, page)
        self.assertIn('les lits libres', page)
        # Envoi forcé d'un lit retenu par le brouillon : refusé
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        res = self.url_open('/hotel/booking/submit', data={
            'csrf_token': token, 'room_id': self.room_a.id, 'checkin': str(self.ci),
            'checkout': str(self.co), 'guests': 1, 'booking_type': 'bed',
            'bed_ids': [bed2.id], 'last_name': 'Client', 'first_name': 'Web', 'birthdate': '1990-01-01', 'street': '1 rue Test', 'phone': '0550000000', 'email': 'web.pris@example.com'},
            allow_redirects=False)
        self.assertEqual(res.status_code, 200)
        self.assertIn('indisponible', res.text)
        self.assertFalse(self.env['hotel.reservation'].search(
            [('partner_id.email', '=', 'web.pris@example.com')]))

    def test_website_bed_booking_one_line_per_bed(self):
        page = self.url_open('/hotel/room/%s?checkin=%s&checkout=%s&guests=2&booking_type=bed'
                             % (self.room_a.id, self.ci, self.co))
        self.assertNotIn('Toute la chambre', page.text)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        beds = self.room_a.bed_ids[:2]
        res = self.url_open('/hotel/booking/submit', data={
            'csrf_token': token, 'room_id': self.room_a.id, 'checkin': str(self.ci),
            'checkout': str(self.co), 'guests': 2, 'booking_type': 'bed',
            'bed_ids': beds.ids, 'last_name': 'Client', 'first_name': 'Web', 'birthdate': '1990-01-01', 'street': '1 rue Test', 'phone': '0550000000', 'email': 'web.lits@example.com'},
            allow_redirects=False)
        self.assertIn(res.status_code, (302, 303))
        resa = self.env['hotel.reservation'].search([('line_ids.room_id', '=', self.room_a.id)])
        self.assertEqual(resa.booking_type, 'bed')
        self.assertEqual(len(resa.line_ids), 2)
        self.assertEqual(resa.line_ids.bed_id, beds)
        # type le moins cher au lit (prix lit 1000) choisi automatiquement
        self.assertEqual(resa.room_type_id, self.rtype)
        self.assertEqual(resa.amount_total, 2 * 1000 * 2)

    def test_reservation_form_beds_tab(self):
        """Par lit : onglet « Lits » à la place de « Chambres » ; choisir un lit
        remplit sa chambre (proposition : lits restants de la chambre entamée)."""
        self.env.ref('base.user_admin').password = 'admin'
        resa = self.env['hotel.reservation'].create({
            'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
            'adults': 1, 'booking_type': 'bed',
            'line_ids': [(0, 0, {'bed_id': self.room_a.bed_ids[0].id})]})
        code = """
            const fail = (msg) => console.error(msg);
            const tabs = [...document.querySelectorAll('.o_notebook_headers .nav-link')]
                .map((a) => a.textContent.trim());
            if (!tabs.includes('Lits') || tabs.includes('Chambres')) {
                fail('Onglets inattendus : ' + tabs.join(', '));
            } else if (!document.querySelector('.o_field_one2many th[data-name="bed_id"]')) {
                fail('Colonne Lit absente');
            } else {
                document.querySelector('.o_field_x2many_list_row_add button').click();
                setTimeout(() => {
                    const input = document.querySelector('.o_selected_row [name="bed_id"] input');
                    input.click();
                    setTimeout(() => {
                        const items = [...document.querySelectorAll('.o-autocomplete--dropdown-item')]
                            .map((i) => i.textContent.trim()).filter((t) => t.startsWith('BT-'));
                        // Ordre du site : d'abord les lits restants de la chambre entamée (A)
                        if (!items.length || !items[0].startsWith('BT-A') || !items[1].startsWith('BT-A')) {
                            fail('Lits proposés inattendus : ' + items.join(', '));
                            return;
                        }
                        document.querySelector('.o-autocomplete--dropdown-item a').click();
                        setTimeout(() => {
                            const room = document.querySelector('.o_selected_row [name="room_id"]');
                            if (room && room.textContent.includes('BT-A')) {
                                document.querySelector('.o_form_button_cancel').click();
                                setTimeout(() => console.log('test successful'), 1000);
                            } else {
                                fail('Chambre non déduite : ' + (room && room.textContent));
                            }
                        }, 1500);
                    }, 1500);
                }, 1500);
            }
        """
        self.browser_js(
            '/odoo/action-hotel_management.action_hotel_reservation/%s' % resa.id,
            code, ready="!!document.querySelector('.o_form_view .o_notebook')",
            login='admin', timeout=90)


@tagged('post_install', '-at_install')
class TestRoomPublish(BookingTypeCommon, HttpCase):
    """Bouton Publier / Dépublier : seules les chambres publiées apparaissent
    sur le site et peuvent y être réservées."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_rooms()

    def test_new_room_unpublished_and_buttons(self):
        room = self.env['hotel.room'].create({'name': 'BT-NEW', 'capacity': 2})
        self.assertFalse(room.website_published)
        room.action_website_publish()
        self.assertTrue(room.website_published)
        room.action_website_unpublish()
        self.assertFalse(room.website_published)
        for xid in ('hotel_management.view_hotel_room_form',
                    'hotel_management.view_hotel_room_config_form'):
            arch = self.env.ref(xid).arch
            self.assertIn('action_website_publish', arch)
            self.assertIn('action_website_unpublish', arch)

    def test_unpublished_room_hidden_and_not_bookable(self):
        self.room_b.action_website_unpublish()
        url = '/hotel/rooms?checkin=%s&checkout=%s&guests=1&booking_type=%s'
        for btype in ('room', 'bed'):
            page = self.url_open(url % (self.ci, self.co, btype)).text
            self.assertNotIn('Chambre BT-B<', page)
            self.assertIn('Chambre BT-A', page)
        self.assertNotIn('Chambre BT-B<', self.url_open('/hotel/rooms').text)
        self.assertNotIn('Chambre BT-B<', self.url_open('/').text)
        detail = self.url_open('/hotel/room/%s' % self.room_b.id, allow_redirects=False)
        self.assertIn(detail.status_code, (301, 302, 303))
        # envoi forcé sur la chambre dépubliée : refusé
        page = self.url_open('/hotel/room/%s' % self.room_a.id).text
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        res = self.url_open('/hotel/booking/submit', data={
            'csrf_token': token, 'room_id': self.room_b.id, 'checkin': str(self.ci),
            'checkout': str(self.co), 'guests': 1, 'booking_type': 'room',
            'last_name': 'Client', 'first_name': 'Web', 'birthdate': '1990-01-01',
            'street': '1 rue Test', 'phone': '0550000000', 'email': 'web.depub@example.com'},
            allow_redirects=False)
        self.assertEqual(res.status_code, 200)
        self.assertIn('Chambre introuvable', res.text)
        self.assertFalse(self.env['hotel.reservation'].search(
            [('partner_id.email', '=', 'web.depub@example.com')]))
