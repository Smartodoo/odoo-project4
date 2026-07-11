from odoo import fields, models


class DocumentPageInherit(models.Model):
    _inherit = 'document.page'

    projet_commercial_id = fields.Many2one(
        'commercial.projet',
        string="Projet Commercial",
    )
