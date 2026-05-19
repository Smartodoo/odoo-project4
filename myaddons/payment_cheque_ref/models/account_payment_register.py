from odoo import models, fields, api


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    cheque_reference = fields.Char(
        string="Référence du chèque",
        help="Numéro / référence du chèque (visible uniquement si le mode "
             "de paiement est Chèque).",
    )
    payment_method_code = fields.Char(
        related='payment_method_line_id.code',
        string="Code mode paiement",
        readonly=True,
    )

    # Override pour rendre cashbox_id éditable + auto-fill par journal
    cashbox_id = fields.Many2one(
        'cashbox',
        string='Caisse',
        required=True,
        compute='_compute_cashbox_id_by_journal',
        store=True,
        readonly=False,
    )

    @api.depends('journal_id')
    def _compute_cashbox_id_by_journal(self):
        """Mappe le journal -> caisse :
        - Banque  -> 'Caisse Verte'
        - Espèces -> 'Caisse Espèce'
        - Autre   -> caisse de l'utilisateur (fallback).
        """
        Cashbox = self.env['cashbox']
        for rec in self:
            cashbox = Cashbox
            jtype = rec.journal_id.type if rec.journal_id else False
            if jtype == 'bank':
                cashbox = Cashbox.search([('name', '=', 'Caisse Verte')], limit=1)
            elif jtype == 'cash':
                cashbox = Cashbox.search([('name', '=', 'Caisse Espèce')], limit=1)
            if not cashbox:
                if rec.env.user.has_group('base.group_system'):
                    cashbox = Cashbox.search([('name', '=', 'Caisse Principale')], limit=1)
                else:
                    cashbox = Cashbox.search(
                        [('responsible_ids', '=', rec.env.user.id)], limit=1
                    )
            rec.cashbox_id = cashbox.id if cashbox else False

    def _create_payment_vals_from_wizard(self, batch_result):
        """Injecte cashbox_id, sale_order_id, purchase_order_id et cheque_reference
        dans les valeurs de création du paiement, AVANT que account.payment.create
        ne tourne — pour que caisse2 puisse créer ses caisse.entry/caisse.expense
        au bon moment."""
        vals = super()._create_payment_vals_from_wizard(batch_result)
        self._inject_caisse_vals(vals)
        return vals

    def _create_payment_vals_from_batch(self, batch_result):
        vals = super()._create_payment_vals_from_batch(batch_result)
        self._inject_caisse_vals(vals)
        return vals

    def _inject_caisse_vals(self, vals):
        """Injecte les valeurs nécessaires pour que caisse2 crée ses records
        au moment du super().create(). Couvre les deux directions :
        - Facture client (out_invoice) -> sale_order_id
        - Facture fournisseur (in_invoice) -> purchase_order_id

        Détection robuste : on lit les SO/PO depuis les lignes de la facture
        (plus fiable que le matching texte sur invoice_origin)."""
        if self.cashbox_id:
            vals['cashbox_id'] = self.cashbox_id.id
        if self.cheque_reference:
            vals['cheque_reference'] = self.cheque_reference

        # 1) Détection automatique via lignes de facture
        invoices = self.line_ids.move_id.filtered(
            lambda m: m.move_type in ('out_invoice', 'in_invoice', 'out_refund', 'in_refund')
        )
        if invoices:
            if 'sale_order_id' in self._fields and 'sale_order_id' not in vals:
                sale_orders = invoices.mapped('invoice_line_ids.sale_line_ids.order_id')
                if sale_orders:
                    vals['sale_order_id'] = sale_orders[0].id
            if 'purchase_order_id' in self._fields and 'purchase_order_id' not in vals:
                purchase_orders = invoices.mapped('invoice_line_ids.purchase_line_id.order_id')
                if purchase_orders:
                    vals['purchase_order_id'] = purchase_orders[0].id

        # 2) Fallback sur le contexte fourni par vente_personalisation
        if 'sale_order_id' in self._fields and 'sale_order_id' not in vals and self.sale_order_id:
            vals['sale_order_id'] = self.sale_order_id.id
        if 'purchase_order_id' in self._fields and 'purchase_order_id' not in vals and self.purchase_order_id:
            vals['purchase_order_id'] = self.purchase_order_id.id

    def _create_payments(self):
        """Filet de sécurité : si la référence n'a pas été propagée via vals,
        on la pose explicitement après création."""
        payments = super()._create_payments()
        if payments and self.cheque_reference:
            payments.write({'cheque_reference': self.cheque_reference})
        return payments
