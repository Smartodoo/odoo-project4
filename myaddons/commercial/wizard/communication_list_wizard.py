from odoo import api, fields, models


class CommunicationListWizard(models.TransientModel):
    _name = 'commercial.communication.list.wizard'
    _description = 'Liste des communications'

    partner_id = fields.Many2one('res.partner', string='Contact', required=True)
    communication_ids = fields.One2many(
        related='partner_id.communication_ids', string='Communications', readonly=True)

    def action_print_communications(self):
        """Imprime la liste des communications."""
        return self.env.ref('commercial.action_report_communication_list').report_action(self)

    def action_add_communication(self):
        """Ouvre le formulaire pour ajouter une nouvelle communication."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ajouter une communication',
            'res_model': 'commercial.communication',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.partner_id.id,
            },
        }