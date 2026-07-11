from odoo import models, fields, api


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    beton_expense_ids = fields.One2many(
        'beton.caisse.expense',
        'purchase_id',
        string='Paiements caisse',
    )
    beton_payment_count = fields.Integer(
        string='Nb paiements',
        compute='_compute_beton_payments',
        store=True,
    )
    beton_amount_paid = fields.Monetary(
        string='Montant paye (caisse)',
        compute='_compute_beton_payments',
        store=True,
        currency_field='currency_id',
    )
    beton_amount_residual = fields.Monetary(
        string='Reste a payer (caisse)',
        compute='_compute_beton_payments',
        store=True,
        currency_field='currency_id',
    )
    beton_is_fully_paid = fields.Boolean(
        string='Totalement paye (caisse)',
        compute='_compute_beton_payments',
        store=True,
    )
    beton_payment_state = fields.Selection([
        ('not_paid', 'Non paye'),
        ('partial', 'Partiel'),
        ('paid', 'Paye'),
    ], string='Etat paiement caisse',
        compute='_compute_beton_payments',
        store=True,
    )

    @api.depends('beton_expense_ids', 'beton_expense_ids.state', 'beton_expense_ids.amount_paid', 'amount_total')
    def _compute_beton_payments(self):
        for rec in self:
            approved = rec.beton_expense_ids.filtered(lambda e: e.state == 'approuve')
            rec.beton_payment_count = len(approved)
            rec.beton_amount_paid = sum(approved.mapped('amount_paid'))
            rec.beton_amount_residual = rec.amount_total - rec.beton_amount_paid
            rec.beton_is_fully_paid = rec.beton_amount_paid >= rec.amount_total and rec.amount_total > 0
            if rec.beton_amount_paid <= 0:
                rec.beton_payment_state = 'not_paid'
            elif rec.beton_is_fully_paid:
                rec.beton_payment_state = 'paid'
            else:
                rec.beton_payment_state = 'partial'

    def action_register_beton_payment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Enregistrer un paiement',
            'res_model': 'beton.register.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'purchase.order',
                'active_id': self.id,
            },
        }

    def action_view_beton_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Paiements caisse',
            'res_model': 'beton.caisse.expense',
            'view_mode': 'tree,form',
            'domain': [('purchase_id', '=', self.id)],
            'context': {'default_purchase_id': self.id},
        }
