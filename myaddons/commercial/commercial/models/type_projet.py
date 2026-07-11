from odoo import models, fields


class CommercialTypeProjet(models.Model):
    _name = 'commercial.type.projet'
    _description = 'Type de projet'

    name = fields.Char(string="Nom", required=True)
