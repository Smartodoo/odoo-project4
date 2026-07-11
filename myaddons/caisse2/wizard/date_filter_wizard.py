from odoo import models, fields, api
from odoo.exceptions import UserError


class DateFilterWizard(models.TransientModel):
    _name = 'date.filter.wizard'
    _description = 'Assistant de Filtrage par Date'

    date_from = fields.Date(string='Date début', required=True)
    date_to = fields.Date(string='Date fin', required=True)
    model_name = fields.Char(string='Modèle', required=True)
    date_field = fields.Char(string='Champ Date', default='date')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise UserError("La date de début doit être inférieure ou égale à la date de fin.")

    def action_apply_filter(self):
        self.ensure_one()

        # Construire le domaine de filtrage
        domain = [
            (self.date_field, '>=', self.date_from),
            (self.date_field, '<=', self.date_to)
        ]

        # Retourner l'action avec le domaine
        return {
            'name': f'Résultats du {self.date_from.strftime("%d/%m/%Y")} au {self.date_to.strftime("%d/%m/%Y")}',
            'type': 'ir.actions.act_window',
            'res_model': self.model_name,
            'view_mode': 'tree,form',
            'domain': domain,
            'context': dict(self.env.context, create=False),
        }
