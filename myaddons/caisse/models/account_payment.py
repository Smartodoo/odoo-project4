from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    caisse_session_id = fields.Many2one(
        'caisse.session', string="Caisse", index=True, copy=False,
        ondelete='restrict',
        help="Session de caisse dans laquelle ce paiement en espèces a été encaissé.")

    def action_post(self):
        """Un paiement en espèces de l'auberge validé alors qu'une caisse est
        ouverte y est rattaché automatiquement (encaissement depuis la
        réservation ou depuis la facture)."""
        res = super().action_post()
        Session = self.env['caisse.session']
        for payment in self.filtered(
                lambda p: p.hotel_reservation_id and not p.caisse_session_id
                and p._caisse_is_cash()):
            session = Session._get_open_session(payment.company_id)
            if session:
                payment.sudo().caisse_session_id = session
        return res

    def _caisse_is_cash(self):
        """Espèces : mode « Espèces » de l'auberge, ou journal de type caisse
        (remboursements, dont la ligne sortante n'a pas de mode auberge)."""
        self.ensure_one()
        return self.hotel_payment_mode == 'cash' or self.journal_id.type == 'cash'


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
