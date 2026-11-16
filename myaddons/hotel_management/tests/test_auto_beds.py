from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAutoBeds(TransactionCase):
    """Création d'une chambre : lits créés automatiquement selon la capacité."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rtype = cls.env['hotel.room.type'].create({'name': 'Type auto', 'list_price': 2000})

    def _room(self, **vals):
        values = {'name': 'AB-101', 'room_type_id': self.rtype.id, 'capacity': 3,
                  'bed_price': 1500}
        values.update(vals)
        return self.env['hotel.room'].create(values)

    def test_beds_created_from_capacity(self):
        room = self._room()
        self.assertEqual(sorted(room.bed_ids.mapped('name')),
                         ['AB-101-L1', 'AB-101-L2', 'AB-101-L3'])
        self.assertEqual(set(room.bed_ids.mapped('price')), {1500})

    def test_bed_name_editable(self):
        room = self._room()
        bed = room.bed_ids.filtered(lambda b: b.name == 'AB-101-L1')
        bed.name = 'Lit fenêtre'
        self.assertIn('Lit fenêtre', room.bed_ids.mapped('name'))

    def test_top_up_when_beds_given(self):
        room = self._room(bed_ids=[(0, 0, {'name': 'Superposé haut'})])
        self.assertEqual(len(room.bed_ids), 3)
        self.assertIn('Superposé haut', room.bed_ids.mapped('name'))
        self.assertIn('AB-101-L1', room.bed_ids.mapped('name'))

    def test_form_creation(self):
        from odoo.tests import Form
        view = 'hotel_management.view_hotel_room_config_form'
        with Form(self.env['hotel.room'], view=view) as f:
            f.room_type_id = self.rtype
            f.name = 'AB-202'
            f.capacity = 3
            self.assertEqual(len(f.bed_ids), 3)
            with f.bed_ids.edit(0) as line:
                self.assertEqual(line.name, 'AB-202-L1')
                line.name = 'Lit porte'
            f.capacity = 2
            self.assertEqual(len(f.bed_ids), 2)
        room = f.record
        self.assertEqual(sorted(room.bed_ids.mapped('name')), ['AB-202-L1', 'Lit porte'])
        self.assertEqual(set(room.bed_ids.mapped('price')), {2000})

    def test_capacity_increase_adds_beds(self):
        room = self._room(capacity=2)
        room.bed_ids.filtered(lambda b: b.name == 'AB-101-L2').name = 'Lit fenêtre'
        room.capacity = 4
        self.assertEqual(sorted(room.bed_ids.mapped('name')),
                         ['AB-101-L1', 'AB-101-L2', 'AB-101-L3', 'Lit fenêtre'])

    def test_capacity_increase_form(self):
        from odoo.tests import Form
        room = self._room(capacity=2)
        view = 'hotel_management.view_hotel_room_config_form'
        with Form(room, view=view) as f:
            f.capacity = 5
            self.assertEqual(len(f.bed_ids), 5)
            f.capacity = 3
            self.assertEqual(len(f.bed_ids), 3)
        self.assertEqual(sorted(room.bed_ids.mapped('name')),
                         ['AB-101-L1', 'AB-101-L2', 'AB-101-L3'])

    def test_rename_room_renames_beds(self):
        room = self._room(capacity=3)
        room.bed_ids.filtered(lambda b: b.name == 'AB-101-L3').name = 'Lit fenêtre'
        room.bed_ids.filtered(lambda b: b.name == 'AB-101-L2').active = False
        room.name = 'AB-105'
        names = room.with_context(active_test=False).bed_ids.mapped('name')
        self.assertEqual(sorted(names), ['AB-105-L1', 'AB-105-L2', 'Lit fenêtre'])

    def test_rename_room_form(self):
        from odoo.tests import Form
        room = self._room(capacity=2)
        with Form(room, view='hotel_management.view_hotel_room_config_form') as f:
            f.name = 'AB-110'
            self.assertEqual(len(f.bed_ids), 2)
        self.assertEqual(sorted(room.bed_ids.mapped('name')), ['AB-110-L1', 'AB-110-L2'])

    def _book(self, bed, days_from_today):
        from datetime import timedelta
        from odoo import fields as f
        ci = f.Date.today() + timedelta(days=days_from_today)
        partner = self.env['res.partner'].create({'name': 'Client lits', 'hotel_birthdate': '1990-01-01'})
        resa = self.env['hotel.reservation'].create({
            'partner_id': partner.id, 'checkin': ci, 'checkout': ci + timedelta(days=2),
            'booking_type': 'bed', 'line_ids': [(0, 0, {'bed_id': bed.id})]})
        resa.action_confirm()
        return resa

    def test_capacity_decrease_removes_beds(self):
        room = self._room(capacity=5, rental_mode='bed')
        room.capacity = 3
        self.assertEqual(sorted(room.bed_ids.mapped('name')),
                         ['AB-101-L1', 'AB-101-L2', 'AB-101-L3'])
        self.assertFalse(self.env['hotel.bed'].with_context(active_test=False).search(
            [('room_id', '=', room.id), ('active', '=', False)]))

    def test_capacity_decrease_keeps_history_and_busy(self):
        room = self._room(capacity=4, rental_mode='bed')
        beds = {b.name: b for b in room.bed_ids}
        old = self._book(beds['AB-101-L4'], -10)
        old.state = 'checkout'
        self._book(beds['AB-101-L3'], 5)            # réservation à venir
        room.capacity = 2
        # L4 (historique) archivé, L2 (libre) supprimé, L3 (à venir) gardé
        self.assertEqual(sorted(room.bed_ids.mapped('name')), ['AB-101-L1', 'AB-101-L3'])
        self.assertFalse(beds['AB-101-L4'].active)
        self.assertFalse(beds['AB-101-L2'].exists())
        # L1 et L3 pris (à venir) : impossible de descendre à 1
        self._book(beds['AB-101-L1'], 20)
        with self.assertRaises(UserError):
            room.capacity = 1
        self.assertEqual(len(room.bed_ids), 2)
