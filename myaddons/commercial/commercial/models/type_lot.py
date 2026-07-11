from odoo import models, fields


class CommercialTypeLot(models.Model):
    _name = 'commercial.type.lot'
    _description = 'Type de Lot'
    _rec_name = 'name'

    name = fields.Char(string="Type de lot", required=True)