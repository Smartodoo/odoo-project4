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
