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


class WebsiteCommon(BookingTypeCommon):
    """Seules les chambres du test sont publiées."""

    @classmethod
    def _setup_web(cls):
        cls._setup_rooms()
        ours = cls.room_a | cls.room_b | cls.room_c | cls.room_d
        cls.env['hotel.room'].search([('id', 'not in', ours.ids)]).write(
            {'website_published': False})

    def _qs(self, booking_type, guests, separate=False):
        return 'checkin=%s&checkout=%s&guests=%s&booking_type=%s%s' % (
            self.ci, self.co, guests, booking_type, '&separate=1' if separate else '')

    def _book_page(self, booking_type, guests, separate=False, rtype=None):
        return self.url_open('/hotel/book?type_id=%s&%s' % (
            (rtype or self.rtype).id, self._qs(booking_type, guests, separate))).text

    def _submit(self, booking_type, guests, separate=False, room=None, beds=None,
                email='web@example.com', rtype=None):
        page = self._book_page(booking_type, guests, separate, rtype)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        data = {'csrf_token': token, 'type_id': (rtype or self.rtype).id,
                'checkin': str(self.ci), 'checkout': str(self.co), 'guests': guests,
                'booking_type': booking_type, 'last_name': 'Client', 'first_name': 'Web',
                'birthdate': '1990-01-01', 'street': '1 rue Test', 'phone': '0550000000',
                'email': email}
        if separate:
            data['separate'] = '1'
        if room:
            data['room_id'] = room.id
        if beds:
            data['bed_ids'] = beds.ids
        return self.url_open('/hotel/booking/submit', data=data, allow_redirects=False)


@tagged('post_install', '-at_install')
class TestBookingTypeWebsite(WebsiteCommon, HttpCase):
    """Site : recherche -> formules (types) avec prix -> chambres / lits
    proposés par le système (mêmes règles que la réception)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_web()

    def test_search_lists_types_with_price(self):
        default = self.url_open('/hotel/rooms?checkin=%s&checkout=%s&guests=1'
                                % (self.ci, self.co)).text
        self.assertIn('Choisissez le type de location', default)
        page = self.url_open('/hotel/rooms?' + self._qs('bed', 2)).text
        self.assertIn('Type lits', page)
        self.assertIn('/hotel/book?type_id=%s' % self.rtype.id, page)
        # 2 lits x 1000 x 2 nuits
        self.assertRegex(page, r'4[\s\u202f\xa0,.]?000')
        # case « séparés » : au lit et plus d'une personne seulement
        self.assertIn('name="separate"', page)
        self.assertNotIn('name="separate"', self.url_open('/hotel/rooms?' + self._qs('bed', 1)).text)
        self.assertNotIn('name="separate"', self.url_open('/hotel/rooms?' + self._qs('room', 2)).text)
        # catalogue sans dates : chambres publiées seulement
        catalogue = self.url_open('/hotel/rooms').text
        self.assertIn('Chambre BT-B', catalogue)
        self.assertNotIn('Chambre 101<', catalogue)

    def test_room_proposals(self):
        self._book_bed(self.room_a.bed_ids[0])
        self._book_room(self.room_d)
        page = self._book_page('room', 2)
        self.assertIn('id="room_%s"' % self.room_b.id, page)
        self.assertIn('id="room_%s"' % self.room_c.id, page)
        self.assertNotIn('id="room_%s"' % self.room_d.id, page)   # réservée
        self.assertNotIn('id="room_%s"' % self.room_a.id, page)   # un lit loué
        # capacité du type : 3 -> aucune chambre vide de 3
        typed = self.env['hotel.room.type'].create(
            {'name': 'Triple web', 'room_price': 900, 'capacity': 3})
        self.assertIn('Plus de disponibilité', self._book_page('room', 2, rtype=typed))
        # chambre non proposée refusée ; chambre proposée acceptée, prix du type
        res = self._submit('room', 2, room=self.room_a)
        self.assertEqual(res.status_code, 200)
        self.assertIn("plus disponible pour cette formule", res.text)
        res = self._submit('room', 2, room=self.room_b, email='room.web@example.com')
        self.assertIn(res.status_code, (302, 303))
        resa = self.env['hotel.reservation'].search([('partner_id.email', '=', 'room.web@example.com')])
        self.assertEqual(resa.line_ids.room_id, self.room_b)
        self.assertEqual(resa.room_type_id, self.rtype)
        self.assertEqual(resa.floor_id, self.floor)
        self.assertEqual(resa.amount_total, 400 * 2)
        self.assertEqual(resa.state, 'draft')

    def test_bed_together_and_separate(self):
        # A : 3 lits dont 2 loués -> 1 libre ; B : 2 lits dont 1 loué -> 1 libre
        self._book_bed(self.room_a.bed_ids[0])
        self._book_bed(self.room_a.bed_ids[1])
        self._book_bed(self.room_b.bed_ids[0])
        gaps = self.room_a.bed_ids[2] | self.room_b.bed_ids[1]
        # ensemble : aucune chambre partielle de 2 lits libres -> dernier
        # recours interdit (le groupe ne tient pas dans une chambre partielle)
        page = self._book_page('bed', 2)
        self.assertIn('Plus de disponibilité', page)
        self.assertNotIn('id="bed_%s"' % self.room_c.bed_ids[0].id, page)
        # séparés : les deux trous (chambres différentes)
        page = self._book_page('bed', 2, separate=True)
        for bed in gaps:
            self.assertIn('id="bed_%s"' % bed.id, page)
        self.assertNotIn('id="bed_%s"' % self.room_c.bed_ids[0].id, page)
        # deux chambres sans accepter d'être séparés : refusé
        res = self._submit('bed', 2, beds=gaps)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(self.env['hotel.reservation'].search(
            [('partner_id.email', '=', 'web@example.com')]))
        # lit d'une chambre libre (non proposée) : refusé
        res = self._submit('bed', 2, separate=True, beds=self.room_c.bed_ids)
        self.assertIn('non proposé', res.text)
        # séparés : accepté, une ligne par lit, prix lit du type
        res = self._submit('bed', 2, separate=True, beds=gaps, email='sep.web@example.com')
        self.assertIn(res.status_code, (302, 303))
        resa = self.env['hotel.reservation'].search([('partner_id.email', '=', 'sep.web@example.com')])
        self.assertEqual(resa.booking_type, 'bed')
        self.assertEqual(resa.bed_placement, 'fill')
        self.assertEqual(resa.line_ids.bed_id, gaps)
        self.assertEqual(resa.amount_total, 2 * 1000 * 2)

    def test_bed_together_partial_room(self):
        self._book_bed(self.room_a.bed_ids[0])     # A : 2 lits libres
        self._book_bed(self.room_b.bed_ids[0])     # B : 1 lit libre
        # ensemble, et même « séparés » : A loge tout le groupe
        for separate in (False, True):
            page = self._book_page('bed', 2, separate=separate)
            for bed in self.room_a.bed_ids[1:]:
                self.assertIn('id="bed_%s"' % bed.id, page)
            self.assertNotIn('id="bed_%s"' % self.room_c.bed_ids[0].id, page)
        res = self._submit('bed', 2, beds=self.room_a.bed_ids[1:], email='tog.web@example.com')
        self.assertIn(res.status_code, (302, 303))
        resa = self.env['hotel.reservation'].search([('partner_id.email', '=', 'tog.web@example.com')])
        self.assertEqual(resa.bed_placement, 'together')
        self.assertEqual(resa.line_ids.room_id, self.room_a)

    def test_bed_free_room_when_no_partial(self):
        """Aucune chambre partielle : chambre libre avec lits = personnes."""
        page = self._book_page('bed', 3)
        for bed in self.room_a.bed_ids:
            self.assertIn('id="bed_%s"' % bed.id, page)
        self.assertNotIn('id="bed_%s"' % self.room_b.bed_ids[0].id, page)
        res = self._submit('bed', 3, beds=self.room_a.bed_ids, email='free.web@example.com')
        self.assertIn(res.status_code, (302, 303))
        resa = self.env['hotel.reservation'].search([('partner_id.email', '=', 'free.web@example.com')])
        self.assertEqual(resa.bed_placement, 'together')
        self.assertEqual(len(resa.line_ids), 3)


@tagged('post_install', '-at_install')
class TestReservationFormBedsTab(BookingTypeCommon, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_rooms()

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
class TestRoomPublish(WebsiteCommon, HttpCase):
    """Bouton Publier / Dépublier : seules les chambres publiées apparaissent
    sur le site et peuvent y être réservées."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_web()

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
        page = self._book_page('room', 2)
        self.assertNotIn('id="room_%s"' % self.room_b.id, page)
        self.assertIn('id="room_%s"' % self.room_c.id, page)
        self.assertNotIn('Chambre BT-B<', self.url_open('/hotel/rooms').text)
        self.assertNotIn('Chambre BT-B<', self.url_open('/').text)
        detail = self.url_open('/hotel/room/%s' % self.room_b.id, allow_redirects=False)
        self.assertIn(detail.status_code, (301, 302, 303))
        res = self._submit('room', 2, room=self.room_b, email='web.depub@example.com')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(self.env['hotel.reservation'].search(
            [('partner_id.email', '=', 'web.depub@example.com')]))
