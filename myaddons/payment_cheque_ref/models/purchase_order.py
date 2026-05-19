from odoo import models, fields, api


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    invoice_payment_state = fields.Selection([
        ('not_paid', 'Non payé'),
        ('partial', 'Partiellement payé'),
        ('paid', 'Payé'),
    ], string="État paiement", compute='_compute_invoice_payment_state', store=True)

    @api.depends('invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.state', 'invoice_ids.move_type')
    def _compute_invoice_payment_state(self):
        for po in self:
            invoices = po.invoice_ids.filtered(
                lambda m: m.move_type == 'in_invoice' and m.state == 'posted'
            )
            if not invoices:
                po.invoice_payment_state = 'not_paid'
                continue
            paid_states = ('paid', 'in_payment', 'reversed')
            partial_states = ('partial',)
            if all(inv.payment_state in paid_states for inv in invoices):
                po.invoice_payment_state = 'paid'
            elif any(inv.payment_state in (paid_states + partial_states) for inv in invoices):
                po.invoice_payment_state = 'partial'
            else:
                po.invoice_payment_state = 'not_paid'
