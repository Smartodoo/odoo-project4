from odoo import fields, models


class CommunicationInteresseWizard(models.TransientModel):
    _name = 'commercial.communication.interesse.wizard'
    _description = 'Liste des communications - Client intéressé'

    client_interesse_id = fields.Many2one(
        'commercial.client.interesse', string='Client intéressé', required=True)
    communication_ids = fields.One2many(
        related='client_interesse_id.communication_ids', string='Communications', readonly=True)

    def action_add_communication(self):
        """Ouvre le formulaire pour ajouter une nouvelle communication."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ajouter une communication',
            'res_model': 'commercial.communication',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_client_interesse_id': self.client_interesse_id.id,
            },
        }
