from odoo import models, api


class AccountPaymentMethod(models.Model):
    _inherit = 'account.payment.method'

    @api.model
    def _get_payment_method_information(self):
        res = super()._get_payment_method_information()
        # Code 'cheque_ref' — distinct des codes du module beton_caisse
        res['cheque_ref'] = {'mode': 'multi', 'type': ('bank',)}
        return res
