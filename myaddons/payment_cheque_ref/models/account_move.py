from odoo import models, fields


class AccountMove(models.Model):
    _inherit = 'account.move'

    custom_invoice_number = fields.Char(
        string="Numéro de facture",
        copy=False,
        help="Numéro de facture personnalisé. Si renseigné, il sera affiché "
             "sur le rapport PDF à la place du numéro généré par Odoo.",
    )
