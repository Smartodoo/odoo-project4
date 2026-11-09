from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    hotel_reservation_id = fields.Many2one(
        'hotel.reservation', string="Réservation hôtel", copy=False)

    def _post(self, soft=True):
        """À la validation d'une facture de l'auberge, les acomptes déjà
        encaissés sur la réservation sont déduits automatiquement (lettrage)."""
        posted = super()._post(soft=soft)
        reservations = posted.filtered(
            lambda m: m.move_type == 'out_invoice' and m.hotel_reservation_id
        ).hotel_reservation_id
        if reservations:
            reservations._hotel_reconcile_payments()
        return posted
