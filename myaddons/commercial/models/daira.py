from odoo import models, fields


class CommercialDaira(models.Model):
    _name = 'commercial.daira'
    _description = 'Daïra'
    _order = 'name'

    name = fields.Char(string="Nom", required=True)
    wilaya_id = fields.Many2one('commercial.wilaya', string="Wilaya", required=True, ondelete='cascade')
    country_id = fields.Many2one(related='wilaya_id.country_id', string="Pays", store=True, readonly=True)
    commune_ids = fields.One2many('commercial.commune', 'daira_id', string="Communes")
