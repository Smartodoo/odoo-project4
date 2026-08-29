from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    hotel_reservation_ids = fields.One2many(
        'hotel.reservation', 'partner_id', string="Réservations")
    hotel_reservation_count = fields.Integer(
        string="Nb réservations", compute='_compute_hotel_reservation_count')

    def _compute_hotel_reservation_count(self):
        groups = self.env['hotel.reservation'].read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['partner_id'])
        mapping = {g['partner_id'][0]: g['partner_id_count'] for g in groups}
        for rec in self:
            rec.hotel_reservation_count = mapping.get(rec.id, 0)

    def action_view_hotel_reservations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Réservations",
            'res_model': 'hotel.reservation',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
