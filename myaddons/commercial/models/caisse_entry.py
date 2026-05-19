from odoo import models, fields, api


class CaisseEntry(models.Model):
    _inherit = 'caisse.entry'

    commercial_remboursement_ids = fields.One2many(
        'commercial.remboursement', 'caisse_entry_id',
        string='Remboursements commerciaux',
    )
    refunded_amount = fields.Float(
        string='Montant remboursé',
        compute='_compute_refund_state',
        store=True,
    )
    refund_state = fields.Selection([
        ('non_rembourse', 'Non remboursé'),
        ('partiellement_rembourse', 'Partiellement remboursé'),
        ('totalement_rembourse', 'Totalement remboursé'),
    ], string='État remboursement',
        compute='_compute_refund_state',
        store=True,
        default='non_rembourse',
    )

    @api.depends(
        'commercial_remboursement_ids.state',
        'commercial_remboursement_ids.montant_rembourse',
        'amount', 'amount_paid',
    )
    def _compute_refund_state(self):
        for rec in self:
            total = sum(
                r.montant_rembourse for r in rec.commercial_remboursement_ids
                if r.state == 'confirme'
            )
            rec.refunded_amount = total
            base_amount = rec.amount_paid or rec.amount
            if total <= 0:
                rec.refund_state = 'non_rembourse'
            elif base_amount and total >= base_amount:
                rec.refund_state = 'totalement_rembourse'
            else:
                rec.refund_state = 'partiellement_rembourse'
