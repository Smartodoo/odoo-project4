from odoo import models, fields


class PrintRemboursementWizard(models.TransientModel):
    _name = 'commercial.print.remboursement.wizard'
    _description = 'Sélectionner un remboursement à imprimer'

    versement_id = fields.Many2one('commercial.versement', string="Versement", required=True)
    remboursement_id = fields.Many2one(
        'commercial.remboursement', string="Remboursement",
        domain="[('versement_id', '=', versement_id)]")

    def action_print(self):
        self.ensure_one()
        return self.env.ref(
            'commercial.action_report_decharge_remboursement'
        ).report_action(self.remboursement_id)
