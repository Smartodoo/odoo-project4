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
        f.guest_count = 4
        f.children = 1
        self.assertEqual(len(f.guest_ids), 3)
        with f.line_ids.new() as line:
            line.bed_id = self.r3.bed_ids[0]
        for bed in self.r3.bed_ids[1:]:
            with f.line_ids.new() as line:
                line.bed_id = bed
        with f.line_ids.new() as line:
            line.bed_id = self.r2.bed_ids[0]
        with f.guest_ids.edit(0) as guest:
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

    def test_persons_include_children(self):
        f = Form(self.env['hotel.reservation'])
        f.partner_id = self.partner
        f.guest_count = 3
        f.children = 1
        self.assertEqual(f.adults, 2)
        self.assertEqual(f.guest_count, 3)
        self.assertEqual(len(f.guest_ids), 2)
        f.children = 2
        self.assertEqual(f.adults, 1)
        self.assertEqual(f.guest_count, 3)

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
