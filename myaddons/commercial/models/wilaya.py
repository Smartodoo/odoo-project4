from odoo import models, fields


class CommercialWilaya(models.Model):
    _name = 'commercial.wilaya'
    _description = 'Wilaya / Région'
    _order = 'code, name'

    name = fields.Char(string="Nom", required=True)
    code = fields.Char(string="Code")
    country_id = fields.Many2one('res.country', string="Pays", required=True, ondelete='cascade')
    daira_ids = fields.One2many('commercial.daira', 'wilaya_id', string="Daïras")
