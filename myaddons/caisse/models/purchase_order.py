from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare

from odoo.addons.hotel_management.models.account_payment import HOTEL_PAYMENT_MODES


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    caisse_amount_paid = fields.Monetary(
        string="Déjà payé", compute='_compute_caisse_amounts',
        currency_field='currency_id')
    caisse_amount_due = fields.Monetary(
        string="Reste à payer", compute='_compute_caisse_amounts',
        currency_field='currency_id')

    @api.depends('amount_total', 'invoice_ids.state', 'invoice_ids.amount_residual')
    def _compute_caisse_amounts(self):
        for order in self:
            paid = 0.0
            for bill in order.sudo().invoice_ids.filtered(lambda m: m.state == 'posted'):
                settled = bill.amount_total - bill.amount_residual
                paid += -settled if bill.move_type == 'in_refund' else settled
            order.caisse_amount_paid = paid
            order.caisse_amount_due = max(order.amount_total - paid, 0.0)

    def action_caisse_pay(self):
        """Bouton « Encaisser » de l'achat (comme sur la réservation)."""
        self.ensure_one()
        if self.state != 'purchase':
            raise UserError(_("Confirmez l'achat avant de le payer."))
        if self.caisse_amount_due <= 0:
            raise UserError(_("L'achat %s est déjà entièrement payé.", self.name))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Encaisser — %s", self.name),
            'res_model': 'caisse.purchase.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }


class CaissePurchasePaymentWizard(models.TransientModel):
    """Fenêtre « Encaisser » d'un achat : crée (si besoin) et valide la
    facture fournisseur, puis enregistre le paiement. En espèces, l'argent
    sort de la caisse ouverte (Dépenses > Achats)."""
    _name = 'caisse.purchase.payment.wizard'
    _description = "Payer un achat"

    order_id = fields.Many2one('purchase.order', string="Achat", required=True, readonly=True)
    partner_id = fields.Many2one(related='order_id.partner_id', string="Fournisseur")
    currency_id = fields.Many2one(related='order_id.currency_id')
    company_id = fields.Many2one(related='order_id.company_id')
    amount_total = fields.Monetary(related='order_id.amount_total', string="Total achat")
    amount_paid = fields.Monetary(related='order_id.caisse_amount_paid')
    amount_due = fields.Monetary(related='order_id.caisse_amount_due')

    payment_mode = fields.Selection(
        HOTEL_PAYMENT_MODES, string="Mode de paiement", required=True, default='cash')
    journal_id = fields.Many2one(
        'account.journal', string="Journal", compute='_compute_journal_id')
    caisse_session_id = fields.Many2one(
        'caisse.session', string="Caisse", compute='_compute_journal_id')
    amount = fields.Monetary(
        string="Montant", required=True, currency_field='currency_id',
        compute='_compute_amount', store=True, readonly=False, precompute=True)
    date = fields.Date(string="Date", required=True, default=fields.Date.context_today)
    cheque_reference = fields.Char(string="N° de chèque")
    memo = fields.Char(string="Mémo")

    @api.depends('order_id')
    def _compute_amount(self):
        for wiz in self:
            wiz.amount = wiz.order_id.caisse_amount_due

    @api.depends('payment_mode', 'company_id')
    def _compute_journal_id(self):
        Journal = self.env['account.journal'].sudo()
        Session = self.env['caisse.session']
        for wiz in self:
            company = wiz.company_id or self.env.company
            line = Journal._hotel_get_payment_method_line(wiz.payment_mode, company)
            if not line:
                Journal._hotel_setup_payment_modes()
                line = Journal._hotel_get_payment_method_line(wiz.payment_mode, company)
            wiz.journal_id = line.journal_id
            wiz.caisse_session_id = (Session._get_open_session(company)
                                     if wiz.payment_mode == 'cash' else False)

    def _get_bills(self):
        """Factures de l'achat à payer : créées si besoin, puis validées."""
        self.ensure_one()
        order = self.order_id
        if order.invoice_status == 'to invoice':
            order.action_create_invoice()
        bills = order.sudo().invoice_ids.filtered(lambda m: m.move_type == 'in_invoice')
        for bill in bills.filtered(lambda m: m.state == 'draft'):
            if not bill.invoice_date:
                bill.invoice_date = self.date
            bill.action_post()
        return bills.filtered(
            lambda m: m.state == 'posted' and m.payment_state in ('not_paid', 'partial'))

    def action_confirm(self):
        self.ensure_one()
        order = self.order_id
        rounding = self.currency_id.rounding or 0.01
        if float_compare(self.amount, 0.0, precision_rounding=rounding) <= 0:
            raise UserError(_("Le montant doit être supérieur à zéro."))
        if float_compare(self.amount, order.caisse_amount_due, precision_rounding=rounding) > 0:
            raise UserError(_(
                "Le montant (%(amount)s) dépasse le reste à payer (%(due)s).",
                amount=self.amount, due=order.caisse_amount_due))
        if self.payment_mode == 'cash' and not self.caisse_session_id:
            raise UserError(_(
                "Aucune caisse n'est ouverte.\n\n"
                "L'achat est payé en espèces : l'argent sort de la caisse. Ouvrez "
                "la caisse (application Caisse > Caisse du jour) avant de payer."))
        if self.payment_mode == 'cheque' and not self.cheque_reference:
            raise UserError(_("Indiquez le numéro du chèque."))
        journal = self.journal_id
        method_line = self.env['account.journal']._hotel_get_outbound_method_line(journal)
        if not journal or not method_line:
            raise UserError(_(
                "Aucun journal de paiement sortant n'est configuré pour le mode « %s ».",
                dict(HOTEL_PAYMENT_MODES)[self.payment_mode]))

        bills = self._get_bills()
        if not bills:
            raise UserError(_(
                "Rien à facturer pour l'achat %s : vérifiez les quantités "
                "reçues (achat facturé à la réception).", order.name))
        residual = sum(bills.mapped('amount_residual'))
        if float_compare(self.amount, residual, precision_rounding=rounding) > 0:
            raise UserError(_(
                "Le montant (%(amount)s) dépasse ce qui est facturé et non payé "
                "(%(residual)s). Les quantités non reçues ne sont pas encore facturées.",
                amount=self.amount, residual=residual))

        memo = " — ".join(filter(None, [
            order.name,
            self.payment_mode == 'cheque' and _("Chèque n° %s", self.cheque_reference),
            self.memo]))
        register = self.env['account.payment.register'].sudo().with_context(
            active_model='account.move', active_ids=bills.ids).create({
                'journal_id': journal.id,
                'payment_method_line_id': method_line.id,
                'amount': self.amount,
                'payment_date': self.date,
                'communication': memo,
                'group_payment': True,
            })
        payments = register._create_payments()
        order.message_post(body=_(
            "Paiement fournisseur : %(amount)s %(currency)s (%(mode)s) — %(payment)s.",
            amount=self.amount, currency=self.currency_id.symbol or '',
            mode=dict(HOTEL_PAYMENT_MODES)[self.payment_mode],
            payment=', '.join(payments.mapped('name'))))
        return {'type': 'ir.actions.act_window_close'}
