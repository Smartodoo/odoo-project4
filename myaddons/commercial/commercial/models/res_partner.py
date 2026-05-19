from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    contact_category = fields.Selection(
        [('interne', 'Interne'), ('externe', 'Externe')],
        string='Catégorie de contact',
        default='externe',

    )
