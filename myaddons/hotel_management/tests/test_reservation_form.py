from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
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
        cls.type_dorm = Type.create({'name': 'RF Dortoir', 'bed_price': 1000})
        cls.type_other = Type.create({'name': 'RF Autre', 'room_price': 3000, 'bed_price': 1000})
        Room = cls.env['hotel.room']
        # chambres de la base hors service : seules celles du test sont proposées
        Room.search([]).write({'technical_state': 'out_of_service'})

        cls.floor = cls.env['hotel.floor'].create({'name': 'RF étage'})

        def room(name, cap):
            return Room.create({'name': name, 'capacity': cap, 'floor_id': cls.floor.id})
        cls.r3 = room('RF-3', 3)
        cls.r2 = room('RF-2', 2)
        cls.partner = cls.env['res.partner'].create({
            'hotel_last_name': 'RF', 'hotel_first_name': 'Test', 'phone': '0550000001', 'street': '1 rue Test', 'hotel_id_type': 'cni', 'hotel_id_number': 'ID0001', 'hotel_birthdate': '1990-01-01'})

    def _new(self, **vals):
        values = {'checkin': self.ci, 'checkout': self.co, 'booking_type': 'bed',
                  'room_type_id': self.type_dorm.id}
        values.update(vals)
        return self.env['hotel.reservation'].new(values)

    def test_room_type_does_not_filter_proposals(self):
        """Le type de chambre fixe le prix, il ne filtre plus les chambres."""
        with_type = self._new(guest_count=2).proposed_bed_ids._origin
        without = self._new(room_type_id=False, guest_count=2).proposed_bed_ids._origin
        self.assertEqual(with_type, self.r2.bed_ids)
        self.assertEqual(without, self.r2.bed_ids)

    def test_bed_order_like_website(self):
        """Par lit : seulement les chambres dont le nombre de lits libres =
        personnes ; à défaut personnes + 1, + 2…"""
        # 2 personnes : seulement la chambre de 2 lits (pas celle de 3)
        resa = self._new(guest_count=2)
        beds = resa.proposed_bed_ids._origin
        self.assertEqual(beds, self.r2.bed_ids)
        self.assertEqual(resa.proposed_bed_order, ','.join(map(str, beds.ids)))
        # 3 personnes : seulement la chambre de 3 lits
        self.assertEqual(self._new(guest_count=3).proposed_bed_ids._origin, self.r3.bed_ids)
        # 1 personne : aucune chambre de 1 lit -> chambres de 2 lits (1 + 1)
        self.assertEqual(self._new(guest_count=1).proposed_bed_ids._origin, self.r2.bed_ids)
        # 4 personnes : aucune chambre assez grande -> tout, la plus libre d'abord
        beds = self._new(guest_count=4).proposed_bed_ids._origin
        self.assertEqual(beds[:3], self.r3.bed_ids)
        self.assertEqual(beds[3:], self.r2.bed_ids)
        # Chambre partiellement occupée avec 2 lits libres = 2 personnes :
        # seuls ses lits sont proposés
        other = self.env['hotel.reservation'].create({
            'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
            'booking_type': 'bed', 'line_ids': [(0, 0, {'bed_id': self.r3.bed_ids[0].id})]})
        other.action_confirm()
        beds = self._new(guest_count=2).proposed_bed_ids._origin
        self.assertEqual(beds, self.r3.bed_ids[1:])
        # 1 personne : aucune chambre (partielle ou libre) avec 1 lit libre ;
        # i = 1 -> 2 lits libres : la chambre partielle r3 passe avant r2 libre
        self.assertEqual(self._new(guest_count=1).proposed_bed_ids._origin, self.r3.bed_ids[1:])
        # 3 personnes : r3 n'a plus que 2 lits libres, aucune chambre de 3 ->
        # tout, la plus libre d'abord, partielle avant libre à égalité
        beds = self._new(guest_count=3).proposed_bed_ids._origin
        self.assertEqual(beds, self.r3.bed_ids[1:] + self.r2.bed_ids)
        # Autres dates : r3 libre en entier -> règle des chambres disponibles
        later = self.co + timedelta(days=5)
        beds = self._new(guest_count=2, checkin=later,
                         checkout=later + timedelta(days=1)).proposed_bed_ids._origin
        self.assertEqual(beds, self.r2.bed_ids)
        # Lits déjà choisis : comptés comme placés (2 personnes, 1 lit choisi
        # dans r2 -> reste 1 personne -> la chambre où il reste 1 lit : r2)
        bed = self.r2.bed_ids[0]
        resa = self._new(guest_count=2, line_ids=[(0, 0, {'bed_id': bed.id, 'bed_ids': [(6, 0, bed.ids)]})])
        self.assertEqual(resa.proposed_bed_ids._origin, self.r2.bed_ids[1:])

    def test_room_order_like_website(self):
        Room = self.env['hotel.room']
        (self.r2 | self.r3).technical_state = 'out_of_service'
        two = Room.create({'name': 'RF-R2', 'capacity': 2})
        big = Room.create({'name': 'RF-R3', 'capacity': 3})
        small = Room.create({'name': 'RF-R1', 'capacity': 1})

        def proposed(guests):
            return self._new(booking_type='room', room_type_id=self.type_other.id,
                             guest_count=guests).proposed_room_ids._origin
        # nombre de lits = personnes uniquement
        self.assertEqual(proposed(2), two)
        self.assertEqual(proposed(3), big)
        self.assertEqual(proposed(1), small)
        # plus de chambre de 2 lits libre -> 2 + 1 = chambre de 3 lits
        two.maintenance = True
        self.assertEqual(proposed(2), big)
        two.maintenance = False
        # 4 personnes : aucune assez grande -> toutes, la plus grande d'abord
        self.assertEqual(list(proposed(4)), [big, two, small])

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
        f.floor_id = self.floor
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
        # Autre adulte : nom, prénom, naissance, téléphone, pièce obligatoires
        with self.assertRaises(AssertionError):
            with f.guest_adult_ids.edit(0) as guest:
                guest.last_name = 'Benali'
                guest.first_name = 'Amine'
        with f.guest_adult_ids.edit(0) as guest:
            guest.last_name = 'Benali'
            guest.first_name = 'Amine'
            guest.birthdate = '1988-08-08'
            guest.phone = '0550101010'
            guest.id_type = 'cni'
            guest.id_number = 'CNI-77'
        with f.guest_adult_ids.edit(1) as guest:
            guest.last_name = 'Benali'
            guest.first_name = 'Sofia'
            guest.birthdate = '1990-09-09'
            guest.phone = '0550202020'
            guest.id_type = 'passport'
            guest.id_number = 'P-88'
        # Enfant : rien d'obligatoire
        with f.guest_child_ids.edit(0) as child:
            child.first_name = 'Ines'
        resa = f.save()
        self.assertEqual(resa.adults, 3)
        labels = sorted(resa.guest_ids.mapped('label'))
        self.assertEqual(labels, ['Adulte', 'Adulte', 'Enfant'])
        self.assertIn('Benali Amine', resa.guest_ids.mapped('name'))
        # Moins de personnes : les fiches en trop disparaissent
        resa.write({'adults': 2, 'children': 0,
                    'line_ids': [(2, line.id) for line in resa.line_ids[2:]]})
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
        f.floor_id = self.floor
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
        f.partner_street = '5 rue des Oliviers'
        f.partner_id_type = 'passport'
        f.partner_id_number = 'P445566'
        with f.line_ids.new() as line:
            line.bed_id = self.r2.bed_ids[0]
        resa = f.save()
        self.assertTrue(resa.partner_id)
        self.assertEqual(resa.partner_id.hotel_last_name, 'Haddad')
        self.assertEqual(resa.partner_id.phone, '0550000000')
        self.assertEqual(str(resa.partner_id.hotel_birthdate), '1992-05-04')
        self.assertIn('Haddad', resa.partner_id.name)
        self.assertEqual((resa.partner_id.street, resa.partner_id.hotel_id_type,
                          resa.partner_id.hotel_id_number),
                         ('5 rue des Oliviers', 'passport', 'P445566'))
        # Champs obligatoires du client principal dans le formulaire
        f = Form(self.env['hotel.reservation'])
        f.floor_id = self.floor
        f.partner_last_name = 'Mansouri'
        with self.assertRaises(AssertionError):
            f.save()
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            self.env['hotel.reservation'].create({
                'checkin': self.ci, 'checkout': self.co, 'booking_type': 'bed'})

    def test_identity_blocks_confirm_and_checkin(self):
        """Confirmation et check-in refusés tant que le client principal et les
        autres adultes n'ont pas toutes leurs informations ; le site web, lui,
        confirme quand même (pièces complétées par la réception)."""
        from odoo.exceptions import UserError
        incomplete = self.env['res.partner'].create({
            'hotel_last_name': 'Partiel', 'hotel_first_name': 'Client',
            'hotel_birthdate': '1990-01-01', 'phone': '0550000000'})
        resa = self.env['hotel.reservation'].create({
            'partner_id': incomplete.id, 'checkin': self.ci, 'checkout': self.co,
            'booking_type': 'bed', 'adults': 2,
            'line_ids': [(0, 0, {'bed_id': b.id}) for b in self.r2.bed_ids]})
        with self.assertRaises(UserError) as err:
            resa.action_confirm()
        msg = str(err.exception)
        self.assertIn('Client principal', msg)
        self.assertIn('Adresse', msg)
        self.assertIn('Adulte 2', msg)
        self.assertEqual(resa.state, 'draft')
        # Site web : confirmée malgré tout
        resa.with_context(hotel_skip_identity_check=True).action_confirm()
        self.assertEqual(resa.state, 'confirmed')
        # Check-in bloqué tant que tout n'est pas complet
        with self.assertRaises(UserError):
            resa.action_checkin()
        incomplete.write({'street': '1 rue A', 'hotel_id_type': 'cni', 'hotel_id_number': 'C1'})
        with self.assertRaises(UserError) as err:
            resa.action_checkin()
        self.assertNotIn('Client principal', str(err.exception))
        resa.guest_adult_ids.write({
            'last_name': 'Autre', 'first_name': 'Adulte', 'birthdate': '1991-01-01',
            'phone': '0551111111', 'id_type': 'passport', 'id_number': 'P1'})
        resa.action_checkin()
        self.assertEqual(resa.state, 'checkin')

    def test_homonym_warning(self):
        """Nom + prénom déjà connus : notification non bloquante, contact créé
        seulement à l'enregistrement."""
        self.env['res.partner'].create({
            'hotel_last_name': 'Brahimi', 'hotel_first_name': 'Nadia',
            'phone': '0770000000', 'hotel_birthdate': '1985-03-02'})
        resa = self._new(partner_last_name=' brahimi', partner_first_name='NADIA ')
        res = resa._onchange_partner_names_create()
        self.assertFalse(resa.partner_id)
        self.assertEqual(res['warning']['type'], 'notification')
        self.assertIn('Brahimi Nadia', res['warning']['message'])
        self.assertIn('02/03/1985', res['warning']['message'])

    def test_id_number_unique(self):
        """N° de pièce déjà utilisé par un autre contact : alerte + refus."""
        Partner = self.env['res.partner']
        Partner.create({'hotel_last_name': 'Haddad', 'hotel_first_name': 'Ali',
                        'hotel_id_number': 'AB123'})
        with self.assertRaises(ValidationError) as err:
            Partner.create({'hotel_last_name': 'Autre', 'hotel_first_name': 'Personne',
                            'hotel_id_number': ' ab123 '})
        self.assertIn('existe déjà', str(err.exception))
        other = Partner.create({'hotel_last_name': 'Autre', 'hotel_first_name': 'P',
                                'hotel_id_number': 'AB1234'})
        with self.assertRaises(ValidationError):
            other.hotel_id_number = 'AB123'
        # Formulaire réservation : alerte immédiate (fenêtre)
        resa = self._new(partner_last_name='Neuf', partner_first_name='Client',
                         partner_id_number='AB123')
        res = resa._onchange_partner_id_number()
        self.assertIn('Haddad Ali', res['warning']['message'])
        self.assertNotEqual(res['warning'].get('type'), 'notification')
        # Nouveau client enregistré avec ce numéro : refusé
        with self.assertRaises(ValidationError):
            self.env['hotel.reservation'].create({
                'checkin': self.ci, 'checkout': self.co, 'booking_type': 'room',
                'partner_last_name': 'Neuf', 'partner_first_name': 'Client',
                'partner_id_number': 'AB123'})
        # Autre adulte du séjour : alerte aussi
        g = self.env['hotel.reservation.guest'].new({'guest_type': 'adult', 'id_number': 'ab123'})
        self.assertTrue(g._onchange_id_number())

    def test_bed_count_equals_guests(self):
        """Location par lit : lits sélectionnés = personnes, sinon refus."""
        beds = self.r2.bed_ids
        self.assertGreaterEqual(len(beds), 2)
        vals = {'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
                'booking_type': 'bed'}
        with self.assertRaises(ValidationError):
            self.env['hotel.reservation'].create(dict(
                vals, adults=1, line_ids=[(0, 0, {'bed_id': b.id}) for b in beds[:2]]))
        with self.assertRaises(ValidationError):
            self.env['hotel.reservation'].create(dict(
                vals, adults=2, line_ids=[(0, 0, {'bed_id': beds[0].id})]))
        resa = self.env['hotel.reservation'].create(dict(
            vals, adults=2, line_ids=[(0, 0, {'bed_id': b.id}) for b in beds[:2]]))
        with self.assertRaises(ValidationError):
            resa.write({'adults': 1})

    def test_guest_contact_created(self):
        """Autres personnes : contact créé/sélectionné au nom + prénom, fiche
        contact remplie, notification si homonyme."""
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
        # Homonyme : notification non bloquante, rien de créé
        g2 = Guest.new({'guest_type': 'adult', 'last_name': 'saidi', 'first_name': 'omar'})
        res = g2._onchange_names_create_partner()
        self.assertFalse(g2.partner_id)
        self.assertEqual(res['warning']['type'], 'notification')
        self.assertIn('Contact existant', res['warning']['message'])
        # ... puis enregistrée quand même : nouveau contact créé à l'enregistrement
        resa.write({'adults': 3, 'children': 1,
                    'line_ids': [(0, 0, {'bed_id': b.id}) for b in self.r3.bed_ids[:2]]})
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
        f.floor_id = self.floor
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
            'booking_type': 'bed', 'guest_count': 3, 'children': 1,
            'line_ids': [(0, 0, {'bed_id': b.id}) for b in self.r3.bed_ids]})
        self.assertEqual((resa.adults, resa.guest_count), (2, 3))

    def test_room_type_independent_of_booking_type(self):
        """Aucun lien entre type de location et type de chambre : tous les
        types sont proposés, et changer de mode garde le type choisi."""
        domain = self.env['hotel.reservation']._fields['room_type_id'].domain
        self.assertFalse(domain)
        f = Form(self.env['hotel.reservation'])
        f.floor_id = self.floor
        f.booking_type = 'bed'
        f.room_type_id = self.type_dorm   # pas de prix chambre
        f.booking_type = 'room'
        self.assertEqual(f.room_type_id, self.type_dorm)
        f.booking_type = 'bed'
        self.assertEqual(f.room_type_id, self.type_dorm)

    def test_floor_filters_and_is_checked(self):
        """Étage : obligatoire dans le formulaire, filtre les propositions,
        chambres d'un autre étage refusées."""
        from odoo.exceptions import ValidationError
        Floor = self.env['hotel.floor']
        f1 = Floor.create({'name': 'RF Étage 1'})
        f2 = Floor.create({'name': 'RF Étage 2'})
        self.r2.floor_id = f1
        other = self.env['hotel.room'].create({'name': 'RF-E2', 'capacity': 2, 'floor_id': f2.id})
        proposed = self._new(guest_count=2, floor_id=f1.id).proposed_bed_ids._origin
        self.assertEqual(proposed, self.r2.bed_ids)
        proposed = self._new(guest_count=2, floor_id=f2.id).proposed_bed_ids._origin
        self.assertEqual(proposed, other.bed_ids)
        arch = self.env['hotel.reservation'].get_view(view_type='form')['arch']
        self.assertRegex(arch, r'name="floor_id"[^>]*required=')
        with self.assertRaises(ValidationError):
            self.env['hotel.reservation'].create({
                'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
                'booking_type': 'room', 'floor_id': f1.id,
                'line_ids': [(0, 0, {'room_id': other.id})]})
        resa = self.env['hotel.reservation'].create({
            'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
            'booking_type': 'room', 'floor_id': f2.id,
            'line_ids': [(0, 0, {'room_id': other.id})]})
        # changer d'étage dans le formulaire retire les chambres de l'autre étage
        new = self.env['hotel.reservation'].new({'floor_id': f1.id, 'line_ids': [
            (0, 0, {'room_id': other.id})]})
        warning = new._onchange_floor_id()
        self.assertFalse(new.line_ids)
        self.assertIn('RF-E2', warning['warning']['message'])
        self.assertEqual(resa.floor_id, f2)

@tagged('post_install', '-at_install')
class TestRoomCreation(TransactionCase):
    """Chambres : ni type, ni mode, ni prix ; capacité modifiable (3 par
    défaut). Les prix sont sur les types de chambre."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))

    def test_room_fields_removed(self):
        Room = self.env['hotel.room']
        for fname in ('room_type_id', 'rental_mode', 'price'):
            self.assertNotIn(fname, Room._fields)
        Type = self.env['hotel.room.type']
        for fname in ('rental_mode', 'default_capacity', 'list_price'):
            self.assertNotIn(fname, Type._fields)
        self.assertIn('room_price', Type._fields)
        self.assertIn('bed_price', Type._fields)

    def test_capacity_default_and_editable(self):
        room = self.env['hotel.room'].create({'name': 'RC-1'})
        self.assertEqual(room.capacity, 3)
        self.assertEqual(len(room.bed_ids), 3)
        for view in ('hotel_management.view_hotel_room_config_form',
                     'hotel_management.view_hotel_room_form'):
            with Form(room, view=view) as f:
                f.capacity = 2
            self.assertEqual(len(room.bed_ids), 2)
            room.capacity = 3

    def test_room_price_is_cheapest_type(self):
        """Sur la chambre : simple « à partir de » (type le moins cher)."""
        Type = self.env['hotel.room.type']
        Type.search([]).write({'active': False})
        Type.create({'name': 'RC A', 'room_price': 5000, 'bed_price': 2000})
        Type.create({'name': 'RC B', 'room_price': 4000})
        room = self.env['hotel.room'].create({'name': 'RC-3'})
        self.assertEqual(room.room_price, 4000)
        self.assertEqual(room.whole_room_price, 4000)
        self.assertEqual(room.bed_price_min, 2000)
        self.assertEqual(set(room.bed_ids.mapped('price')), {2000})

    def test_floor_model(self):
        floor = self.env['hotel.floor'].create({'name': 'RC Rez-de-chaussée', 'sequence': 1})
        room = self.env['hotel.room'].create({
            'name': 'RC-9', 'floor_id': floor.id})
        self.assertEqual(room.floor, 'RC Rez-de-chaussée')
        self.assertEqual(floor.room_count, 1)
        floor.name = 'RC RDC'
        self.assertEqual(room.floor, 'RC RDC')
        self.assertIn('floor_id', self.env['hotel.room']._fields)

