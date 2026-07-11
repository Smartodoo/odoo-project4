from odoo import models, fields


class CommercialReservation(models.Model):
    _name = 'commercial.reservation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Réservation'

    name = fields.Char(string="Référence", required=True)
