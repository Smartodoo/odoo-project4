from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    caisse_session_id = fields.Many2one(
        'caisse.session', string="Caisse", index=True, copy=False,
        ondelete='restrict',
        help="Session de caisse dans laquelle ce paiement en espèces a été encaissé.")
    caisse_kind = fields.Selection([
        ('payment', 'Paiement client'),
        ('refund', 'Remboursement client'),
        ('purchase', 'Achat fournisseur'),
        ('purchase_refund', 'Remboursement fournisseur'),
        ('expense_note', 'Note de frais'),
    ], string="Opération de caisse", copy=False, readonly=True,
        help="Nature de l'opération dans la caisse, fixée au rattachement.")

    def action_post(self):
        """Paiements en espèces validés alors qu'une caisse est ouverte :
        rattachés automatiquement à la caisse.
          - clients de l'auberge (réservation / facture du séjour) ;
          - TOUS les fournisseurs de la société (achats payés en espèces),
            qui exigent une caisse ouverte : l'argent sort de la caisse."""
        Session = self.env['caisse.session']
        for payment in self.filtered(lambda p: p._caisse_is_supplier_cash()):
            if not Session._get_open_session(payment.company_id):
                raise UserError(_(
                    "Aucune caisse n'est ouverte.\n\n"
                    "Le paiement fournisseur %(name)s (%(partner)s) est en espèces : "
                    "l'argent sort de la caisse. Ouvrez la caisse (application "
                    "Caisse > Caisse du jour) avant de le valider.",
                    name=payment.name or payment.memo or '',
                    partner=payment.partner_id.display_name or ''))
        res = super().action_post()
        self._caisse_attach()
        return res

    def _caisse_is_supplier_cash(self):
        self.ensure_one()
        return self.partner_type == 'supplier' and self._caisse_is_cash()

    def _caisse_attach(self):
        """Rattache à la caisse ouverte les paiements en espèces (clients de
        l'auberge, fournisseurs de la société) qui ne le sont pas encore."""
        Session = self.env['caisse.session']
        for payment in self.filtered(
                lambda p: (p.hotel_reservation_id or p.partner_type == 'supplier')
                and not p.caisse_session_id
                and p.state != 'draft' and p._caisse_is_cash()):
            session = Session._get_open_session(payment.company_id)
            if session:
                payment.sudo().write({
                    'caisse_session_id': session.id,
                    'caisse_kind': payment._caisse_get_kind(),
                })

    def _caisse_get_kind(self):
        """Note de frais (payée par la société, ou remboursement à l'employé),
        achat / remboursement fournisseur, paiement / remboursement client."""
        self.ensure_one()
        if self.expense_ids or self._caisse_paid_moves().expense_ids:
            return 'expense_note'
        if self.partner_type == 'supplier':
            return 'purchase' if self.payment_type == 'outbound' else 'purchase_refund'
        return 'refund' if self.payment_type == 'outbound' else 'payment'

    def _caisse_paid_moves(self):
        """Pièces réglées par ce paiement (lettrage) : factures, reçus de
        note de frais… (`reconciled_bill_ids` ignore les reçus de dépense)."""
        self.ensure_one()
        lines = self.sudo().move_id.line_ids
        moves = (lines.matched_debit_ids.debit_move_id.move_id
                 | lines.matched_credit_ids.credit_move_id.move_id)
        return moves - self.sudo().move_id

    def _caisse_refresh_kind(self):
        """Recalcule la nature de l'opération une fois le lettrage fait (le
        paiement est rattaché à la caisse dès sa validation, avant d'être
        lettré avec la note de frais ou la facture qu'il règle)."""
        for payment in self.filtered('caisse_session_id'):
            kind = payment._caisse_get_kind()
            if payment.caisse_kind != kind:
                payment.sudo().caisse_kind = kind

    def _caisse_is_cash(self):
        """Espèces : mode « Espèces » de l'auberge, ou journal de type caisse
        (remboursements, dont la ligne sortante n'a pas de mode auberge)."""
        self.ensure_one()
        return self.hotel_payment_mode == 'cash' or self.journal_id.type == 'cash'


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _caisse_is_cash(self):
        self.ensure_one()
        return (self.payment_method_line_id.hotel_payment_mode == 'cash'
                or self.journal_id.type == 'cash')

    def _caisse_hotel_invoices(self):
        """Factures de l'auberge concernées par ce paiement."""
        return self.line_ids.move_id.filtered('hotel_reservation_id')

    def action_create_payments(self):
        """Bouton « Payer » d'une facture de l'auberge : en espèces, l'argent
        passe obligatoirement par une caisse ouverte (comme « Encaisser »)."""
        for wiz in self:
            invoices = wiz._caisse_hotel_invoices()
            if invoices and wiz._caisse_is_cash() and not self.env[
                    'caisse.session']._get_open_session(invoices[0].company_id):
                raise UserError(_(
                    "Aucune caisse n'est ouverte.\n\n"
                    "Ouvrez la caisse (application Caisse > Caisse du jour) "
                    "avant d'encaisser ou de rembourser en espèces."))
        return super().action_create_payments()

    def _create_payments(self):
        """Le paiement est validé AVANT d'être rattaché à sa réservation
        (cf. hotel_management) : on le rattache donc à la caisse ensuite."""
        payments = super()._create_payments()
        payments._caisse_attach()
        payments._caisse_refresh_kind()
        return payments


class HotelReservationPaymentWizard(models.TransientModel):
    _inherit = 'hotel.reservation.payment.wizard'

    caisse_session_id = fields.Many2one(
        'caisse.session', string="Caisse", compute='_compute_caisse_session_id')

    @api.depends('payment_mode', 'company_id')
    def _compute_caisse_session_id(self):
        Session = self.env['caisse.session']
        for wiz in self:
            wiz.caisse_session_id = Session._get_open_session(
                wiz.company_id or self.env.company) if wiz.payment_mode == 'cash' else False

    def action_confirm(self):
        """Espèces : l'argent passe obligatoirement par une caisse ouverte."""
        for wiz in self:
            if wiz.payment_mode == 'cash' and not self.env['caisse.session']._get_open_session(
                    wiz.reservation_id.company_id):
                raise UserError(_(
                    "Aucune caisse n'est ouverte.\n\n"
                    "Ouvrez la caisse (application Caisse > Caisse du jour) "
                    "avant d'encaisser ou de rembourser en espèces."))
        return super().action_confirm()


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        """Paiement validé depuis sa pièce comptable (ex. note de frais payée
        par la société) : en espèces, il exige une caisse ouverte et y est
        rattaché, comme un paiement validé depuis le paiement lui-même."""
        payments = self.origin_payment_id.filtered(
            lambda p: not p.caisse_session_id and p._caisse_is_supplier_cash())
        Session = self.env['caisse.session']
        for payment in payments:
            if not Session._get_open_session(payment.company_id):
                raise UserError(_(
                    "Aucune caisse n'est ouverte.\n\n"
                    "Le paiement %(name)s est en espèces : l'argent sort de la "
                    "caisse. Ouvrez la caisse (application Caisse > Caisse du "
                    "jour) avant de le valider.",
                    name=payment.memo or payment.partner_id.display_name or ''))
        posted = super()._post(soft=soft)
        posted.origin_payment_id._caisse_attach()
        return posted


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    def _caisse_is_cash(self):
        self.ensure_one()
        return self.payment_mode == 'company_account' and self.journal_id.type == 'cash'

    def _create_move(self):
        """Note de frais payée en espèces par la société : à sa validation,
        l'argent sort de la caisse ouverte (paiement validé et rattaché)."""
        cash = self.filtered(lambda e: e._caisse_is_cash())
        Session = self.env['caisse.session']
        for expense in cash:
            if not Session._get_open_session(expense.company_id):
                raise UserError(_(
                    "Aucune caisse n'est ouverte.\n\n"
                    "La note de frais « %(name)s » est payée en espèces : "
                    "ouvrez la caisse (application Caisse > Caisse du jour) "
                    "avant de la valider.", name=expense.name))
        res = super()._create_move()
        payments = cash.sudo().account_move_id.origin_payment_id.filtered(
            lambda p: p.state == 'draft')
        payments.action_post()
        return res
