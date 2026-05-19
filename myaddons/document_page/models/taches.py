from odoo import models, fields, api


class SuiviTache(models.Model):
    _name = 'suivi.tache'
    _description = "Suivi des tâches périodiques"

    reference = fields.Char(string="Référence", required=True)
    name = fields.Char(string="Nom de la Tâche", )

    description = fields.Text(string="Description")
    montant = fields.Float(string="Montant (DA)")
    date_effectuee = fields.Date(string="Date effectuée", required=True)


    responsable_id = fields.Many2one('res.users', string="Responsable", default=lambda self: self.env.user)


