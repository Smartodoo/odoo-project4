from odoo import models, fields, api


class SelectParkingWizard(models.TransientModel):
    _name = 'commercial.select.parking.wizard'
    _description = "Sélection parking pour impression"

    client_id = fields.Many2one('res.partner', string="Client", required=True)
    parking_id = fields.Many2one(
        'commercial.lot', string="Parking", required=True,
        domain="[('id', 'in', available_parking_ids)]")
    available_parking_ids = fields.Many2many(
        'commercial.lot', compute='_compute_available_parking_ids')

    @api.depends('client_id')
    def _compute_available_parking_ids(self):
        for rec in self:
            if rec.client_id:
                rec.available_parking_ids = rec.client_id.commercial_lot_ids.filtered(
                    lambda l: l.categorie_id and l.categorie_id.type_lot_id
                    and 'PARK' in (l.categorie_id.type_lot_id.name or '').upper()
                )
            else:
                rec.available_parking_ids = self.env['commercial.lot']

    def action_print(self):
        self.ensure_one()
        existing = self.env['commercial.reservation.parking'].search(
            [('client_id', '=', self.client_id.id), ('parking_id', '=', self.parking_id.id)], limit=1)
        if not existing:
            existing = self.env['commercial.reservation.parking'].create({
                'client_id': self.client_id.id,
                'parking_id': self.parking_id.id,
            })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Fiche Parking',
            'res_model': 'commercial.reservation.parking',
            'view_mode': 'form',
            'res_id': existing.id,
        }
