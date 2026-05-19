from odoo import fields, models


class NettoyageCamion(models.Model):
    _name = 'nettoyage.camion'
    _description = 'Camion (Matriculation)'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(string="Matriculation", required=True)
    active = fields.Boolean(string="Actif", default=True)
    company_id = fields.Many2one(
        'res.company', string="Société",
        default=lambda self: self.env.company, index=True,
    )

    _sql_constraints = [
        ('matriculation_unique', 'unique(name, company_id)',
         "Cette matriculation existe déjà pour cette société."),
    ]


class NettoyageChauffeur(models.Model):
    _name = 'nettoyage.chauffeur'
    _description = 'Chauffeur'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(string="Nom du chauffeur", required=True)
    active = fields.Boolean(string="Actif", default=True)
    company_id = fields.Many2one(
        'res.company', string="Société",
        default=lambda self: self.env.company, index=True,
    )
