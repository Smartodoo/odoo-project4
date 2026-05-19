from odoo import models, fields, api


class CommercialAddLotWizard(models.TransientModel):
    _name = 'commercial.add.lot.wizard'
    _description = 'Ajouter des lots'

    partner_id = fields.Many2one('res.partner', required=True)
    lot_ids = fields.Many2many(
        'commercial.lot', string="Lots",
        domain="[('state', 'in', ('disponible', 'en_option'))]",
    )

    def action_confirm(self):
        self.ensure_one()
        PartnerLot = self.env['commercial.partner.lot']
        for lot in self.lot_ids:
            if not PartnerLot.search([
                ('partner_id', '=', self.partner_id.id),
                ('lot_id', '=', lot.id),
            ], limit=1):
                PartnerLot.create({
                    'partner_id': self.partner_id.id,
                    'lot_id': lot.id,
                })
        return {'type': 'ir.actions.act_window_close'}
