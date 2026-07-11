from odoo import models, fields


class CommercialAssocie(models.Model):
    _name = 'commercial.associe'
    _description = 'Associé'
    _rec_name = 'name'

    name = fields.Char(string="Nom", required=True)
    telephone = fields.Char(string="Téléphone")
    adresse = fields.Char(string="Adresse")
