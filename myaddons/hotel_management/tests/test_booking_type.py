import re
from datetime import timedelta

from odoo import fields
from odoo.tests import Form, HttpCase, TransactionCase, tagged


class BookingTypeCommon:
    """Deux dortoirs (A : 4 lits, B : 2 lits), deux chambres entières C et D."""

    @classmethod
    def _setup_rooms(cls):
        cls.ci = fields.Date.today() + timedelta(days=900)
        cls.co = cls.ci + timedelta(days=2)
        rtype = cls.env['hotel.room.type'].create({'name': 'Type lits', 'list_price': 4000})

        def room(name, beds, mode='bed'):
            r = cls.env['hotel.room'].create({
                'name': name, 'room_type_id': rtype.id, 'capacity': beds,
                'room_price': 4000, 'bed_price': 1000, 'rental_mode': mode,
                'website_published': True})
            return r

        cls.room_a = room('BT-A', 3)
        cls.room_b = room('BT-B', 2)
        cls.room_c = room('BT-C', 2, mode='room')
        cls.room_d = room('BT-D', 2, mode='room')
        cls.partner = cls.env['res.partner'].create({
            'name': 'Client lits', 'email': 'lits@example.com', 'hotel_birthdate': '1990-01-01'})

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
        new = Resa.new({'checkin': self.ci, 'checkout': self.co, 'booking_type': 'bed'})
        # Aucune chambre partielle : lits des chambres libres (A et B, pas C)
        self.assertTrue(self.room_a.bed_ids <= new.proposed_bed_ids._origin)
        self.assertTrue(self.room_b.bed_ids <= new.proposed_bed_ids._origin)
        self.assertFalse(self.room_c.bed_ids & new.proposed_bed_ids._origin)

        self._book_bed(self.room_a.bed_ids[0])
        new = Resa.new({'checkin': self.ci, 'checkout': self.co, 'booking_type': 'bed'})
        # A est partiellement réservée : seuls ses lits libres sont proposés
        self.assertEqual(new.proposed_bed_ids._origin, self.room_a.bed_ids[1:])

        # Par chambre : seulement les chambres libres en entier (C ; pas D
        # déjà réservée, ni les dortoirs)
        self._book_room(self.room_d)
        new = Resa.new({'checkin': self.ci, 'checkout': self.co, 'booking_type': 'room'})
        self.assertIn(self.room_c, new.proposed_room_ids._origin)
        self.assertNotIn(self.room_d, new.proposed_room_ids._origin)
        self.assertNotIn(self.room_a, new.proposed_room_ids._origin)

    def test_group_fills_partial_room_first(self):
        """Une fois la chambre partielle pleine, la chambre où le groupe a
        commencé à prendre des lits devient la chambre proposée."""
        self._book_bed(self.room_a.bed_ids[0])
        form = Form(self.env['hotel.reservation'])
        form.partner_id = self.partner
        form.checkin = self.ci
        form.checkout = self.co
        form.booking_type = 'bed'
        form.adults = 1
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
        # Par défaut (sans type choisi) : chambres ET dortoirs, onglets visibles
        default = self.url_open('/hotel/rooms?checkin=%s&checkout=%s&guests=1'
                                % (self.ci, self.co)).text
        self.assertIn('Lit en dortoir', default)
        self.assertIn('Chambre BT-A', self._available_part(default))
        self.assertIn('Chambre BT-C', self._available_part(default))
        self.assertIn('Chambre BT-B', self.url_open('/hotel/rooms').text)
        by_room = self._available_part(self._rooms_page('room'))
        self.assertIn('Chambre BT-C', by_room)
        self.assertNotIn('Chambre BT-D', by_room)   # déjà réservée
        self.assertNotIn('Chambre BT-A', by_room)   # dortoir
        by_bed = self._available_part(self._rooms_page('bed'))
        self.assertIn('Chambre BT-A', by_bed)       # partielle proposée d'abord
        self.assertNotIn('Chambre BT-B', by_bed)
        self.assertNotIn('Chambre BT-C', by_bed)
        self.assertIn('chambres déjà partagées', by_bed)
        # 4 personnes : A n'a plus que 3 lits -> chambres libres proposées
        self.assertNotIn('Chambre BT-A', self._available_part(self._rooms_page('bed', 4)))

    def test_website_bed_booking_one_line_per_bed(self):
        page = self.url_open('/hotel/room/%s?checkin=%s&checkout=%s&guests=2&booking_type=bed'
                             % (self.room_a.id, self.ci, self.co))
        self.assertNotIn('Toute la chambre', page.text)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        beds = self.room_a.bed_ids[:2]
        res = self.url_open('/hotel/booking/submit', data={
            'csrf_token': token, 'room_id': self.room_a.id, 'checkin': str(self.ci),
            'checkout': str(self.co), 'guests': 2, 'booking_type': 'bed',
            'bed_ids': beds.ids, 'name': 'Client Web', 'email': 'web.lits@example.com'},
            allow_redirects=False)
        self.assertIn(res.status_code, (302, 303))
        resa = self.env['hotel.reservation'].search([('line_ids.room_id', '=', self.room_a.id)])
        self.assertEqual(resa.booking_type, 'bed')
        self.assertEqual(len(resa.line_ids), 2)
        self.assertEqual(resa.line_ids.bed_id, beds)
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
                        if (!items.length || items.some((t) => !t.startsWith('BT-A'))) {
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
