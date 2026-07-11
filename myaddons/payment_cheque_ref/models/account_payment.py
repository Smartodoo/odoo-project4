from odoo import models, fields, api


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    cheque_reference = fields.Char(
        string="Référence du chèque",
        copy=False,
        help="Numéro / référence du chèque utilisé pour ce paiement.",
    )
    payment_method_code = fields.Char(
        related='payment_method_line_id.code',
        string="Code mode paiement",
        readonly=True,
        store=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Après la création (qui déclenche caisse2 pour créer les records
        caisse.entry / caisse.expense.supplier), on s'assure que les
        décaissements fournisseurs sont automatiquement APPROUVÉS — et donc
        que la caisse est débitée immédiatement."""
        # Snapshot des IDs existants pour identifier ce qui sera créé
        ExpenseSupplier = self.env['caisse.expense.supplier'].sudo()
        existing_expense_ids = set(ExpenseSupplier.search([]).ids)

        records = super().create(vals_list)

        # Trouver les caisse.expense.supplier nouvellement créés
        new_expenses = ExpenseSupplier.search([
            ('id', 'not in', list(existing_expense_ids)),
            ('state', '=', 'draft'),
        ])

        # Lier au paiement et passer en 'approuve'
        for payment in records:
            if not payment.purchase_order_id:
                continue
            related = new_expenses.filtered(
                lambda e: e.purchase_id.id == payment.purchase_order_id.id
            )
            if related:
                related.write({
                    'payment_id': payment.id,
                    'state': 'approuve',
                })
                # On retire ces enregistrements pour ne pas les ré-affecter
                # à un autre paiement dans la même boucle
                new_expenses -= related

        return records
