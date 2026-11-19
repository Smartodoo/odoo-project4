from odoo import fields, models


class HotelFloor(models.Model):
    """Étages de l'auberge, saisis en configuration ; chaque chambre est
    rattachée à un étage."""
    _name = 'hotel.floor'
    _description = "Étage"
    _order = 'sequence, name'

    name = fields.Char(string="Étage", required=True,
                       help="Ex. : Rez-de-chaussée, 1er étage, E1…")
    sequence = fields.Integer(string="Ordre", default=10)
    active = fields.Boolean(default=True)
    room_ids = fields.One2many('hotel.room', 'floor_id', string="Chambres")
    room_count = fields.Integer(string="Nb chambres", compute='_compute_room_count')

    _name_uniq = models.Constraint('unique(name)', "Cet étage existe déjà.")

    def _compute_room_count(self):
        groups = self.env['hotel.room']._read_group(
            [('floor_id', 'in', self.ids)], ['floor_id'], ['__count'])
        mapping = {floor.id: count for floor, count in groups}
        for rec in self:
            rec.room_count = mapping.get(rec.id, 0)

    def action_view_rooms(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Chambres — %s" % self.name,
            'res_model': 'hotel.room',
            'view_mode': 'list,form',
            'domain': [('floor_id', '=', self.id)],
            'context': {'default_floor_id': self.id},
        }
