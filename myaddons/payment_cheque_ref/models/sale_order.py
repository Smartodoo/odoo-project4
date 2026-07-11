from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    invoice_payment_state = fields.Selection([
        ('not_paid', 'Non payé'),
        ('partial', 'Partiellement payé'),
        ('paid', 'Payé'),
    ], string="État paiement", compute='_compute_invoice_payment_state', store=True)

    @api.depends('invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.state', 'invoice_ids.move_type')
    def _compute_invoice_payment_state(self):
        for so in self:
            invoices = so.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
            )
            if not invoices:
                so.invoice_payment_state = 'not_paid'
                continue
            paid_states = ('paid', 'in_payment', 'reversed')
            partial_states = ('partial',)
            if all(inv.payment_state in paid_states for inv in invoices):
                so.invoice_payment_state = 'paid'
            elif any(inv.payment_state in (paid_states + partial_states) for inv in invoices):
                so.invoice_payment_state = 'partial'
            else:
                so.invoice_payment_state = 'not_paid'
