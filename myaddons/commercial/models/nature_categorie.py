from odoo import models, fields


class CommercialNatureCategorie(models.Model):
    _name = 'commercial.nature.categorie'
    _description = 'Nature de Catégorie'
    _rec_name = 'name'

    name = fields.Char(string="Nature", required=True)