from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    genre = fields.Selection([
        ('homme', 'Homme'),
        ('femme', 'Femme'),
    ], string="Genre")
    qualite = fields.Selection([
        ('assistante_commerciale', 'Assistante commerciale'),
        ('directrice_commerciale', 'Directrice commerciale'),
    ], string="Qualité")
