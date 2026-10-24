from odoo import api, fields, models


class HotelRoomType(models.Model):
    _name = 'hotel.room.type'
    _description = "Type de chambre"
    _order = 'sequence, name'

    name = fields.Char(string="Type", required=True, translate=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(string="Code")
    list_price = fields.Monetary(string="Prix / nuit", currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    default_capacity = fields.Integer(string="Capacité (personnes)", default=2)
    rental_mode = fields.Selection([
        ('room', 'Chambre entière'),
        ('bed', 'Au lit (dortoir)'),
    ], string="Mode de location", default='room', required=True,
        help="Mode appliqué par défaut aux chambres de ce type.")
    amenity_ids = fields.Many2many('hotel.amenity', string="Équipements")
    description = fields.Text(string="Description")
    image = fields.Image(string="Photo")
    active = fields.Boolean(default=True)
    room_ids = fields.One2many('hotel.room', 'room_type_id', string="Chambres")
    room_count = fields.Integer(string="Nb chambres", compute='_compute_room_count')

    def _compute_room_count(self):
        groups = self.env['hotel.room'].read_group(
            [('room_type_id', 'in', self.ids)], ['room_type_id'], ['room_type_id'])
        mapping = {g['room_type_id'][0]: g['room_type_id_count'] for g in groups}
        for rec in self:
            rec.room_count = mapping.get(rec.id, 0)

    def action_view_rooms(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'hotel.room',
            'view_mode': 'kanban,tree,form',
            'domain': [('room_type_id', '=', self.id)],
            'context': {'default_room_type_id': self.id},
        }
