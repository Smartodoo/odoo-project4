from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    hotel_reservation_id = fields.Many2one(
        'hotel.reservation', string="Réservation hôtel", copy=False)
