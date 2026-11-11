from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare

from ..models.account_payment import HOTEL_PAYMENT_KINDS, HOTEL_PAYMENT_MODES


class HotelReservationPaymentWizard(models.TransientModel):
    """Fenêtre « Encaisser » de la réservation : crée un vrai paiement Odoo
    (account.payment) rattaché à la réservation — acompte avant la facture,
    ou paiement du séjour. Cahier des charges §3.1, §4 et §8."""
    _name = 'hotel.reservation.payment.wizard'
    _description = "Encaisser un paiement sur une réservation"

    reservation_id = fields.Many2one(
        'hotel.reservation', string="Réservation", required=True, readonly=True)
    partner_id = fields.Many2one(related='reservation_id.partner_id')
    currency_id = fields.Many2one(related='reservation_id.currency_id')
    company_id = fields.Many2one(related='reservation_id.company_id')
    amount_total = fields.Monetary(related='reservation_id.amount_total')
    amount_paid = fields.Monetary(related='reservation_id.amount_paid')
    amount_due = fields.Monetary(related='reservation_id.amount_due')

    payment_kind = fields.Selection(
        HOTEL_PAYMENT_KINDS, string="Type", required=True,
        compute='_compute_payment_kind', store=True, readonly=False, precompute=True,
        help="Acompte : versé avant la facture, il sera déduit automatiquement "
             "de la facture.\nPaiement : règlement du séjour (ou du solde).")
    payment_mode = fields.Selection(
        HOTEL_PAYMENT_MODES, string="Mode de paiement", required=True,
        default='cash')
    payment_method_line_id = fields.Many2one(
        'account.payment.method.line', string="Journal / mode",
        compute='_compute_payment_method_line_id', store=True, readonly=False,
        precompute=True,
        domain="[('hotel_payment_mode', '=', payment_mode),"
               " ('payment_type', '=', 'inbound'),"
               " ('journal_id.company_id', '=', company_id)]")
    journal_id = fields.Many2one(
        related='payment_method_line_id.journal_id', string="Journal")
    amount = fields.Monetary(
        string="Montant", required=True, currency_field='currency_id',
        compute='_compute_amount', store=True, readonly=False,
        precompute=True)
    date = fields.Date(
        string="Date", required=True, default=fields.Date.context_today)
    cheque_reference = fields.Char(string="N° de chèque")
    memo = fields.Char(string="Mémo")

    @api.depends('reservation_id')
    def _compute_payment_kind(self):
        for wiz in self:
            if self.env.context.get('hotel_refund'):
                wiz.payment_kind = 'refund'
                continue
            has_invoice = wiz.reservation_id.sudo().invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
            wiz.payment_kind = 'payment' if has_invoice else 'deposit'

    @api.depends('reservation_id', 'payment_kind')
    def _compute_amount(self):
        for wiz in self:
            if wiz.payment_kind == 'refund':
                # Trop-perçu remboursable par défaut
                wiz.amount = max(-wiz.reservation_id.amount_due, 0.0)
            else:
                wiz.amount = max(wiz.reservation_id.amount_due, 0.0)

    @api.depends('payment_mode', 'company_id')
    def _compute_payment_method_line_id(self):
        Journal = self.env['account.journal'].sudo()
        for wiz in self:
            company = wiz.company_id or self.env.company
            line = Journal._hotel_get_payment_method_line(wiz.payment_mode, company)
            if not line:
                # Modes pas encore préparés (ex. plan comptable installé après
                # le module) : on les prépare à la volée.
                Journal._hotel_setup_payment_modes()
                line = Journal._hotel_get_payment_method_line(
                    wiz.payment_mode, company)
            wiz.payment_method_line_id = line

    def _get_payment_ref(self):
        self.ensure_one()
        kind = dict(HOTEL_PAYMENT_KINDS)[self.payment_kind]
        parts = ["%s %s" % (kind, self.reservation_id.name)]
        if self.payment_mode == 'cheque' and self.cheque_reference:
            parts.append(_("Chèque n° %s", self.cheque_reference))
        if self.memo:
            parts.append(self.memo)
        return " — ".join(parts)

    def action_confirm(self):
        self.ensure_one()
        reservation = self.reservation_id
        rounding = self.currency_id.rounding or 0.01
        if reservation.state == 'cancel' and self.payment_kind != 'refund':
            raise UserError(_("Impossible d'encaisser sur une réservation annulée."))
        is_refund = self.payment_kind == 'refund'
        if float_compare(self.amount, 0.0, precision_rounding=rounding) <= 0:
            raise UserError(_("Le montant doit être supérieur à zéro."))
        if is_refund:
            if float_compare(self.amount, reservation.amount_paid,
                             precision_rounding=rounding) > 0:
                raise UserError(_(
                    "Le remboursement (%(amount)s) dépasse ce que le client a "
                    "payé (%(paid)s).",
                    amount=self.amount, paid=reservation.amount_paid))
        elif float_compare(self.amount, reservation.amount_due,
                           precision_rounding=rounding) > 0:
            raise UserError(_(
                "Le montant (%(amount)s) dépasse le reste à payer (%(due)s).\n"
                "Corrigez le montant : le trop-perçu n'est pas accepté.",
                amount=self.amount, due=reservation.amount_due))
        if not self.payment_method_line_id:
            raise UserError(_(
                "Aucun journal n'est configuré pour le mode « %s ».\n"
                "Vérifiez la configuration comptable (journaux Espèces / Banque).",
                dict(HOTEL_PAYMENT_MODES)[self.payment_mode]))
        if self.payment_mode == 'cheque' and not self.cheque_reference and not is_refund:
            raise UserError(_("Indiquez le numéro du chèque."))
        journal = self.payment_method_line_id.journal_id
        method_line = self.payment_method_line_id
        if is_refund:
            method_line = self.env['account.journal']._hotel_get_outbound_method_line(journal)
            if not method_line:
                raise UserError(_(
                    "Le journal %s n'a pas de mode de paiement sortant pour "
                    "rembourser.", journal.display_name))

        # sudo : la réception encaisse sans avoir les droits comptables ;
        # le paiement reste tracé au nom de l'utilisateur dans le chatter.
        Payment = self.env['account.payment'].sudo()
        vals = {
            'payment_type': 'outbound' if is_refund else 'inbound',
            'partner_type': 'customer',
            'partner_id': reservation.partner_id.commercial_partner_id.id,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'date': self.date,
            'journal_id': journal.id,
            'payment_method_line_id': method_line.id,
            'memo': self._get_payment_ref(),  # Odoo 18+: ref -> memo
            'hotel_reservation_id': reservation.id,
            'hotel_payment_kind': self.payment_kind,
        }
        # Champ du module payment_cheque_ref, s'il est installé
        if self.cheque_reference and 'cheque_reference' in Payment._fields:
            vals['cheque_reference'] = self.cheque_reference
        payment = Payment.create(vals)
        payment.action_post()

        # Si une facture est déjà validée, le paiement la règle directement.
        reservation._hotel_reconcile_payments()

        mode = dict(HOTEL_PAYMENT_MODES)[self.payment_mode]
        kind = dict(HOTEL_PAYMENT_KINDS)[self.payment_kind]
        reservation.message_post(body=_(
            "%(kind)s encaissé : %(amount)s %(currency)s (%(mode)s) — %(payment)s.",
            kind=kind, amount=self.amount, currency=self.currency_id.symbol or '',
            mode=mode, payment=payment.name))
        return {'type': 'ir.actions.act_window_close'}
