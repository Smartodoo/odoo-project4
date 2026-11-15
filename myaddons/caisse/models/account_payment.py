from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    caisse_session_id = fields.Many2one(
        'caisse.session', string="Caisse", index=True, copy=False,
        ondelete='restrict',
        help="Session de caisse dans laquelle ce paiement en espèces a été encaissé.")

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
                payment.sudo().caisse_session_id = session

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
