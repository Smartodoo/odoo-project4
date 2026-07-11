from odoo import fields, models


class CommercialBanque(models.Model):
    _name = 'commercial.banque'
    _description = 'Banque'
    _rec_name = 'name'

    name = fields.Char(string="Nom de la banque", required=True)
    compte = fields.Char(string="Compte")
    adresse = fields.Char(string="Adresse")
