from datetime import timedelta

from odoo import fields
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReservationForm(TransactionCase):
    """Formulaire de réservation « comme le site » : type de chambre, une
    fiche par personne, propositions triées comme la recherche du site."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))
        cls.ci = fields.Date.today() + timedelta(days=1200)
        cls.co = cls.ci + timedelta(days=2)
        Type = cls.env['hotel.room.type']
        cls.type_dorm = Type.create({'name': 'RF Dortoir', 'list_price': 1000})
        cls.type_other = Type.create({'name': 'RF Autre', 'list_price': 1000})
        Room = cls.env['hotel.room']

        def room(name, cap, rtype, mode='bed', price=1000):
            return Room.create({'name': name, 'room_type_id': rtype.id, 'capacity': cap,
                                'room_price': 3000, 'bed_price': price, 'rental_mode': mode})
        cls.r3 = room('RF-3', 3, cls.type_dorm)
        cls.r2 = room('RF-2', 2, cls.type_dorm)
        cls.rx = room('RF-X', 2, cls.type_other)
        cls.partner = cls.env['res.partner'].create({
            'name': 'Client RF', 'hotel_birthdate': '1990-01-01'})

    def _new(self, **vals):
        values = {'checkin': self.ci, 'checkout': self.co, 'booking_type': 'bed',
                  'room_type_id': self.type_dorm.id}
        values.update(vals)
        return self.env['hotel.reservation'].new(values)

    def test_room_type_filters_proposals(self):
        proposed = self._new().proposed_bed_ids._origin
        self.assertTrue((self.r3.bed_ids | self.r2.bed_ids) <= proposed)
        self.assertFalse(self.rx.bed_ids & proposed)
        # Sans type : tout est proposé
        proposed = self._new(room_type_id=False).proposed_bed_ids._origin
        self.assertTrue(self.rx.bed_ids <= proposed)

    def test_bed_order_like_website(self):
        # 2 personnes : la chambre de 2 lits libres d'abord, puis celle de 3
        resa = self._new(guest_count=2)
        beds = resa.proposed_bed_ids._origin
        self.assertEqual(beds[:2], self.r2.bed_ids)
        self.assertEqual(beds[2:5], self.r3.bed_ids)
        self.assertEqual(resa.proposed_bed_order, ','.join(map(str, beds.ids)))
        # 3 personnes : la chambre de 2 lits (trop petite) passe après
        beds = self._new(guest_count=3).proposed_bed_ids._origin
        self.assertEqual(beds[:3], self.r3.bed_ids)
        # Chambre déjà partagée : proposée en premier
        other = self.env['hotel.reservation'].create({
            'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
            'booking_type': 'bed', 'line_ids': [(0, 0, {'bed_id': self.r3.bed_ids[0].id})]})
        other.action_confirm()
        beds = self._new(guest_count=2).proposed_bed_ids._origin
        self.assertEqual(beds[:2], self.r3.bed_ids[1:])

    def test_room_order_like_website(self):
        Room = self.env['hotel.room']
        two = Room.create({'name': 'RF-R2', 'room_type_id': self.type_other.id, 'capacity': 2,
                           'room_price': 3000, 'rental_mode': 'room'})
        big = Room.create({'name': 'RF-R3', 'room_type_id': self.type_other.id, 'capacity': 3,
                           'room_price': 3000, 'rental_mode': 'room'})
        small = Room.create({'name': 'RF-R1', 'room_type_id': self.type_other.id, 'capacity': 1,
                             'room_price': 3000, 'rental_mode': 'room'})
        resa = self._new(booking_type='room', room_type_id=self.type_other.id, guest_count=2)
        rooms = resa.proposed_room_ids._origin
        # capacité ≥ 2 la plus proche d'abord (RF-R2, puis RF-R3), RF-R1 trop petite à la fin
        # (RF-X, dortoir « par lit », n'est pas louable entière)
        self.assertNotIn(self.rx, rooms)
        self.assertEqual(rooms[0], two)
        self.assertEqual(rooms[1], big)
        self.assertEqual(rooms[-1], small)

    def test_dropdown_follows_order(self):
        resa = self._new(guest_count=2)
        order = resa.proposed_bed_order
        Bed = self.env['hotel.bed'].with_context(hotel_proposal_order=order)
        result = Bed.name_search('', [('id', 'in', resa.proposed_bed_ids._origin.ids)], limit=3)
        self.assertEqual([r[0] for r in result], resa.proposed_bed_ids._origin.ids[:3])
        # Sans contexte : comportement standard
        self.assertTrue(self.env['hotel.bed'].name_search('RF-'))

    def test_guest_blocks_follow_counts(self):
        f = Form(self.env['hotel.reservation'])
        f.partner_id = self.partner
        f.checkin = self.ci
        f.checkout = self.co
        f.booking_type = 'bed'
        f.adults = 3
        f.children = 1
        self.assertEqual(f.guest_count, 4)
        self.assertEqual(len(f.guest_adult_ids), 2)
        self.assertEqual(len(f.guest_child_ids), 1)
        with f.line_ids.new() as line:
            line.bed_id = self.r3.bed_ids[0]
        for bed in self.r3.bed_ids[1:]:
            with f.line_ids.new() as line:
                line.bed_id = bed
        with f.line_ids.new() as line:
            line.bed_id = self.r2.bed_ids[0]
        with f.guest_adult_ids.edit(0) as guest:
            guest.last_name = 'Benali'
            guest.first_name = 'Amine'
        resa = f.save()
        self.assertEqual(resa.adults, 3)
        labels = sorted(resa.guest_ids.mapped('label'))
        self.assertEqual(labels, ['Adulte', 'Adulte', 'Enfant'])
        self.assertIn('Benali Amine', resa.guest_ids.mapped('name'))
        # Moins de personnes : les fiches en trop disparaissent
        resa.write({'adults': 2, 'children': 0})
        self.assertEqual(resa.guest_ids.mapped('label'), ['Adulte'])
        self.assertEqual(resa.guest_count, 2)

    def test_guests_created_outside_form(self):
        resa = self.env['hotel.reservation'].create({
            'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
            'booking_type': 'bed', 'adults': 2, 'children': 2,
            'line_ids': [(0, 0, {'bed_id': b.id}) for b in self.r3.bed_ids]
                        + [(0, 0, {'bed_id': self.r2.bed_ids[0].id})]})
        # Compatibilité : adultes + enfants écrits -> total = 4 personnes
        self.assertEqual(resa.guest_count, 4)
        self.assertEqual(len(resa.guest_ids), 3)
        self.assertEqual(len(resa.guest_ids.filtered(lambda g: g.guest_type == 'child')), 2)

    def test_main_client_typed_without_contact(self):
        """Client principal saisi directement : la fiche client est créée."""
        f = Form(self.env['hotel.reservation'])
        f.checkin = self.ci
        f.checkout = self.co
        f.booking_type = 'bed'
        f.partner_phone = '0550000000'
        f.partner_last_name = 'Haddad'
        self.assertFalse(f.partner_id)
        f.partner_first_name = 'Sara'
        # Nom + prénom saisis : contact créé et sélectionné tout de suite
        self.assertTrue(f.partner_id)
        self.assertEqual(f.partner_id.phone, '0550000000')
        self.assertEqual(f.partner_phone, '0550000000')
        f.partner_birthdate = '1992-05-04'
        with f.line_ids.new() as line:
            line.bed_id = self.r2.bed_ids[0]
        resa = f.save()
        self.assertTrue(resa.partner_id)
        self.assertEqual(resa.partner_id.hotel_last_name, 'Haddad')
        self.assertEqual(resa.partner_id.phone, '0550000000')
        self.assertEqual(str(resa.partner_id.hotel_birthdate), '1992-05-04')
        self.assertIn('Haddad', resa.partner_id.name)
        # Nom seul (sans prénom) : contact créé à l'enregistrement
        f = Form(self.env['hotel.reservation'])
        f.checkin = self.ci
        f.checkout = self.co
        f.booking_type = 'bed'
        f.partner_last_name = 'Mansouri'
        f.partner_birthdate = '1980-01-01'
        self.assertFalse(f.partner_id)
        with f.line_ids.new() as line:
            line.bed_id = self.r2.bed_ids[1]
        self.assertEqual(f.save().partner_id.hotel_last_name, 'Mansouri')
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            self.env['hotel.reservation'].create({
                'checkin': self.ci, 'checkout': self.co, 'booking_type': 'bed'})

    def test_homonym_warning(self):
        """Nom + prénom déjà connus : avertissement, pas de création immédiate."""
        self.env['res.partner'].create({
            'hotel_last_name': 'Brahimi', 'hotel_first_name': 'Nadia',
            'phone': '0770000000', 'hotel_birthdate': '1985-03-02'})
        resa = self._new(partner_last_name=' brahimi', partner_first_name='NADIA ')
        res = resa._onchange_partner_names_create()
        self.assertFalse(resa.partner_id)
        self.assertIn('Brahimi Nadia', res['warning']['message'])
        self.assertIn('02/03/1985', res['warning']['message'])
        # Contact créé avec seulement un nom complet (sans nom/prénom séparés)
        self.env['res.partner'].create({'name': 'Kaci Yacine'})
        res = self._new(partner_last_name='Kaci', partner_first_name='Yacine'
                        )._onchange_partner_names_create()
        self.assertTrue(res and 'Kaci Yacine' in res['warning']['message'])

    def test_guest_contact_created(self):
        """Autres personnes : contact créé/sélectionné au nom + prénom, fiche
        contact remplie, avertissement si homonyme."""
        Guest = self.env['hotel.reservation.guest']
        g = Guest.new({'guest_type': 'adult', 'phone': '0551112233', 'last_name': 'Saidi'})
        g.first_name = 'Omar'
        self.assertFalse(g._onchange_names_create_partner())
        partner = g.partner_id
        self.assertEqual((partner.hotel_last_name, partner.phone), ('Saidi', '0551112233'))
        # Données complétées à l'enregistrement -> recopiées sur le contact
        resa = self.env['hotel.reservation'].create({
            'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
            'booking_type': 'bed', 'adults': 2,
            'line_ids': [(0, 0, {'bed_id': b.id}) for b in self.r2.bed_ids]})
        guest = resa.guest_adult_ids
        guest.write({'partner_id': partner.id, 'last_name': 'Saidi', 'first_name': 'Omar',
                     'birthdate': '1979-07-01', 'id_number': 'X123'})
        self.assertEqual(str(partner.hotel_birthdate), '1979-07-01')
        self.assertEqual(partner.hotel_id_number, 'X123')
        # Homonyme : avertissement, rien de créé
        g2 = Guest.new({'guest_type': 'adult', 'last_name': 'saidi', 'first_name': 'omar'})
        res = g2._onchange_names_create_partner()
        self.assertFalse(g2.partner_id)
        self.assertIn('Contact existant', res['warning']['message'])
        # ... puis enregistrée quand même : nouveau contact créé à l'enregistrement
        resa.write({'adults': 3, 'children': 1})
        other = resa.guest_adult_ids - guest
        self.assertFalse(other.partner_id)
        other.write({'last_name': 'Saidi', 'first_name': 'Omar', 'birthdate': '1990-01-01'})
        self.assertTrue(other.partner_id and other.partner_id != partner)
        self.assertEqual(str(other.partner_id.hotel_birthdate), '1990-01-01')
        # Enfants : pas de contact (un contact doit être majeur)
        child = resa.guest_child_ids
        child.write({'last_name': 'Saidi', 'first_name': 'Lina', 'birthdate': '2015-01-01'})
        self.assertFalse(child.partner_id)
        c2 = Guest.new({'guest_type': 'child', 'last_name': 'Saidi', 'first_name': 'Rayan'})
        c2._onchange_names_create_partner()
        self.assertFalse(c2.partner_id)

    def test_persons_include_children(self):
        f = Form(self.env['hotel.reservation'])
        f.partner_id = self.partner
        f.adults = 2
        f.children = 1
        self.assertEqual(f.guest_count, 3)
        self.assertEqual((len(f.guest_adult_ids), len(f.guest_child_ids)), (1, 1))
        f.children = 2
        self.assertEqual(f.adults, 2)
        self.assertEqual(f.guest_count, 4)
        self.assertEqual((len(f.guest_adult_ids), len(f.guest_child_ids)), (1, 2))
        # Compatibilité site web / imports : écrire le total -> adultes déduits
        resa = self.env['hotel.reservation'].create({
            'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
            'booking_type': 'bed', 'guest_count': 3, 'children': 1})
        self.assertEqual((resa.adults, resa.guest_count), (2, 3))

    def test_room_type_follows_booking_type(self):
        Room = self.env['hotel.room']
        type_private = self.env['hotel.room.type'].create({'name': 'RF Privée', 'rental_mode': 'room'})
        Room.create({'name': 'RF-P1', 'room_type_id': type_private.id, 'capacity': 2,
                     'room_price': 3000, 'rental_mode': 'room'})
        Type = self.env['hotel.room.type']
        domain = self.env['hotel.reservation']._fields['room_type_id'].domain
        self.assertIn('booking_type', domain)
        bed_types = Type.search([('room_ids.rental_mode', '=', 'bed')])
        room_types = Type.search([('room_ids.rental_mode', '=', 'room')])
        self.assertIn(self.type_dorm, bed_types)
        self.assertNotIn(type_private, bed_types)
        self.assertIn(type_private, room_types)
        self.assertNotIn(self.type_dorm, room_types)
        # Passage « par lit » -> « par chambre » : un type dortoir est vidé
        f = Form(self.env['hotel.reservation'])
        f.booking_type = 'bed'
        f.room_type_id = self.type_dorm
        f.booking_type = 'room'
        self.assertFalse(f.room_type_id)
        f.room_type_id = type_private
        f.booking_type = 'room'
        self.assertEqual(f.room_type_id, type_private)


    def test_guests_above_room_type_capacity(self):
        from odoo.exceptions import ValidationError
        self.type_dorm.default_capacity = 2
        vals = {'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
                'booking_type': 'bed', 'room_type_id': self.type_dorm.id, 'guest_count': 3}
        with self.assertRaises(ValidationError) as err:
            self.env['hotel.reservation'].create(vals)
        self.assertIn('Changez le type de chambre', str(err.exception))
        # Avertissement immédiat dans le formulaire
        resa = self._new(guest_count=3)
        warning = resa._onchange_room_type_capacity()
        self.assertTrue(warning and 'RF Dortoir' in warning['warning']['message'])
        # Dans la capacité, ou sans type : accepté
        vals['guest_count'] = 2
        resa = self.env['hotel.reservation'].create(vals)
        with self.assertRaises(ValidationError):
            resa.guest_count = 3
        resa.write({'room_type_id': False, 'guest_count': 3})
        self.assertEqual(resa.guest_count, 3)

    def test_reception_can_create_clients(self):
        reception = self.env.ref('hotel_management.group_hotel_user')
        self.assertIn(self.env.ref('base.group_partner_manager'), reception.all_implied_ids)

    def test_room_booking_lines_valid_in_form(self):
        """Par chambre : la ligne (sans lit unique) ne doit pas être bloquée par
        le champ « Lit » de l'onglet Lits (lignes partagées entre les onglets) ;
        le lit n'est obligatoire qu'en location par lit. Vérifié aussi dans le
        navigateur (réservation par chambre enregistrée puis confirmée)."""
        from lxml import etree
        arch = etree.fromstring(self.env.ref('hotel_management.view_hotel_reservation_form').arch)
        beds = arch.xpath("//page[@name='beds']//field[@name='bed_id']")
        self.assertEqual(len(beds), 1)
        self.assertEqual(beds[0].get('required'), "booking_type == 'bed'")
        room = self.env['hotel.room'].create({
            'name': 'RF-C1', 'room_type_id': self.type_other.id, 'capacity': 2,
            'room_price': 3000, 'rental_mode': 'room'})
        resa = self.env['hotel.reservation'].create({
            'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
            'booking_type': 'room', 'line_ids': [(0, 0, {'room_id': room.id})]})
        resa.action_confirm()
        self.assertEqual(resa.state, 'confirmed')

@tagged('post_install', '-at_install')
class TestRoomCreation(TransactionCase):
    """Création des chambres : capacité du type, prix selon le mode de location."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))
        Type = cls.env['hotel.room.type']
        cls.type_dorm = Type.create({'name': 'RC Dortoir', 'rental_mode': 'bed',
                                     'default_capacity': 3, 'list_price': 1000})
        cls.type_room = Type.create({'name': 'RC Privée', 'rental_mode': 'room',
                                     'default_capacity': 1, 'list_price': 4000})

    def test_capacity_from_type(self):
        room = self.env['hotel.room'].create({'name': 'RC-1', 'room_type_id': self.type_dorm.id})
        self.assertEqual(room.capacity, 3)
        self.assertEqual(len(room.bed_ids), 3)
        f = Form(self.env['hotel.room'], view='hotel_management.view_hotel_room_config_form')
        f.name = 'RC-2'
        f.room_type_id = self.type_room
        self.assertEqual(f.capacity, 1)
        f.room_type_id = self.type_dorm
        self.assertEqual(f.capacity, 3)
        self.assertEqual(f.rental_mode, 'bed')

    def test_bed_room_price_is_sum_of_beds(self):
        room = self.env['hotel.room'].create({
            'name': 'RC-3', 'room_type_id': self.type_dorm.id, 'bed_price': 1500})
        self.assertEqual(room.room_price, 4500)
        self.assertEqual(room.whole_room_price, 4500)
        room.bed_price = 1000
        self.assertEqual(room.room_price, 3000)
        room.capacity = 2
        self.assertEqual(room.room_price, 2000)
        # Chambre entière : le prix saisi reste
        private = self.env['hotel.room'].create({
            'name': 'RC-4', 'room_type_id': self.type_room.id, 'room_price': 5000})
        self.assertEqual(private.room_price, 5000)
        self.assertEqual(private.whole_room_price, 5000)

    def test_capacity_readonly_and_price_from_type(self):
        f = Form(self.env['hotel.room'], view='hotel_management.view_hotel_room_config_form')
        f.name = 'RC-5'
        f.room_type_id = self.type_room
        self.assertEqual(f.room_price, 4000)
        f.room_price = 4500  # prix modifiable
        with self.assertRaises(AssertionError):
            f.capacity = 2  # capacité non modifiable : celle du type
        room = f.save()
        self.assertEqual((room.capacity, room.room_price), (1, 4500))
        # Dortoir : le prix du type devient le prix d'un lit
        f = Form(self.env['hotel.room'], view='hotel_management.view_hotel_room_config_form')
        f.name = 'RC-6'
        f.room_type_id = self.type_dorm
        self.assertEqual(f.bed_price, 1000)
        dorm = f.save()
        self.assertEqual(set(dorm.bed_ids.mapped('price')), {1000})
        self.assertEqual(dorm.room_price, 3000)
        # Création directe sans prix : prix du type
        direct = self.env['hotel.room'].create({'name': 'RC-7', 'room_type_id': self.type_room.id})
        self.assertEqual(direct.room_price, 4000)

    def test_type_capacity_propagates(self):
        room = self.env['hotel.room'].create({'name': 'RC-8', 'room_type_id': self.type_dorm.id})
        self.assertEqual(len(room.bed_ids), 3)
        self.type_dorm.default_capacity = 2
        self.assertEqual(room.capacity, 2)
        self.assertEqual(len(room.bed_ids), 2)

    def test_floor_model(self):
        floor = self.env['hotel.floor'].create({'name': 'RC Rez-de-chaussée', 'sequence': 1})
        room = self.env['hotel.room'].create({
            'name': 'RC-9', 'room_type_id': self.type_room.id, 'floor_id': floor.id})
        self.assertEqual(room.floor, 'RC Rez-de-chaussée')
        self.assertEqual(floor.room_count, 1)
        floor.name = 'RC RDC'
        self.assertEqual(room.floor, 'RC RDC')
        self.assertIn('floor_id', self.env['hotel.room']._fields)

