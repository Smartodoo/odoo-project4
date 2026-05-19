from odoo import api, fields, models


class CommercialRemiseWizard(models.TransientModel):
    _name = 'commercial.remise.wizard'
    _description = 'Wizard de remise'

    partner_id = fields.Many2one('res.partner', string="Contact", required=True)
    partner_lot_id = fields.Many2one(
        'commercial.partner.lot', string="Lot", required=True,
        domain="[('partner_id', '=', partner_id), ('state', 'not in', ('vendu', 'reserve'))]")
    montant_global = fields.Float(
        related='partner_lot_id.montant_global', string="Montant global", readonly=True)
    remise = fields.Float(string="Remise")

    def action_confirm(self):
        self.ensure_one()
        self.partner_lot_id.remise = self.remise
        self.partner_lot_id.lot_id.remise = self.remise
        return {'type': 'ir.actions.act_window_close'}
