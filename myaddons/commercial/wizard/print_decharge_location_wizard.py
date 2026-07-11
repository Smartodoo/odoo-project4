from odoo import models, fields


class PrintDechargeLocationWizard(models.TransientModel):
    _name = 'commercial.print.decharge.location.wizard'
    _description = 'Sélectionner un versement location à imprimer'

    location_id = fields.Many2one(
        'commercial.location', string="Contrat", required=True)
    versement_location_id = fields.Many2one(
        'commercial.versement.location', string="Échéance",
        domain="[('location_id', '=', location_id)]", required=True)

    def action_print(self):
        self.ensure_one()
        return self.env.ref(
            'commercial.action_report_decharge_versement_location'
        ).report_action(self.versement_location_id)
