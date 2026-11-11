from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    hotel_auto_invoice = fields.Boolean(
        string="Facturer automatiquement au départ", default=True,
        help="Au check-out, la facture du séjour est créée et validée "
             "automatiquement ; les acomptes sont déduits.")
    hotel_deposit_percent = fields.Float(
        string="Acompte demandé (%)", default=30.0,
        help="Pourcentage du séjour demandé en acompte aux réservations "
             "en ligne (affiché au client).")
    hotel_deposit_instructions = fields.Text(
        string="Instructions de paiement de l'acompte",
        help="Coordonnées CCP / bancaires affichées au client après une "
             "réservation en ligne et dans l'e-mail de confirmation.")


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hotel_auto_invoice = fields.Boolean(
        related='company_id.hotel_auto_invoice', readonly=False)
    hotel_deposit_percent = fields.Float(
        related='company_id.hotel_deposit_percent', readonly=False)
    hotel_deposit_instructions = fields.Text(
        related='company_id.hotel_deposit_instructions', readonly=False)
