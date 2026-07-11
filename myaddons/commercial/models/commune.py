from odoo import models, fields


class CommercialCommune(models.Model):
    _name = 'commercial.commune'
    _description = 'Commune'
    _order = 'name'

    name = fields.Char(string="Nom", required=True)
    daira_id = fields.Many2one('commercial.daira', string="Daïra", required=True, ondelete='cascade')
    wilaya_id = fields.Many2one(related='daira_id.wilaya_id', string="Wilaya", store=True, readonly=True)
    country_id = fields.Many2one(related='daira_id.country_id', string="Pays", store=True, readonly=True)
