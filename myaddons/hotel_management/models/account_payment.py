from odoo import api, fields, models

# Modes de paiement de l'auberge (cahier des charges §8)
HOTEL_PAYMENT_MODES = [
    ('cash', 'Espèces'),
    ('card', 'Carte bancaire'),
    ('transfer', 'Virement bancaire'),
    ('cheque', 'Chèque'),
]

HOTEL_PAYMENT_KINDS = [
    ('deposit', 'Acompte'),
    ('payment', 'Paiement'),
]


class AccountPaymentMethodLine(models.Model):
    _inherit = 'account.payment.method.line'

    hotel_payment_mode = fields.Selection(
        HOTEL_PAYMENT_MODES, string="Mode (Auberge)",
        help="Mode de paiement proposé à la réception de l'auberge "
             "(Espèces, Carte bancaire, Virement, Chèque).")


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    hotel_reservation_id = fields.Many2one(
        'hotel.reservation', string="Réservation", index=True, copy=False,
        ondelete='set null', tracking=True)
    hotel_payment_kind = fields.Selection(
        HOTEL_PAYMENT_KINDS, string="Type (Auberge)", copy=False,
        help="Acompte : versé avant la facture, déduit automatiquement à la "
             "facturation.\nPaiement : règlement du séjour.")
    hotel_payment_mode = fields.Selection(
        related='payment_method_line_id.hotel_payment_mode',
        string="Mode de paiement", store=True)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payments(self):
        """Un paiement enregistré depuis une facture de l'auberge (bouton
        « Enregistrer un paiement ») est rattaché à sa réservation, pour que
        « Payé » / « Reste à payer » de la réservation restent justes."""
        payments = super()._create_payments()
        for payment in payments.filtered(lambda p: not p.hotel_reservation_id):
            reservation = payment.reconciled_invoice_ids.hotel_reservation_id
            if len(reservation) == 1:
                payment.write({
                    'hotel_reservation_id': reservation.id,
                    'hotel_payment_kind': 'payment',
                })
        return payments


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.model
    def _hotel_get_payment_method_line(self, mode, company=None):
        """Ligne de mode de paiement (entrant) associée à un mode de l'auberge."""
        company = company or self.env.company
        return self.env['account.payment.method.line'].search([
            ('hotel_payment_mode', '=', mode),
            ('payment_type', '=', 'inbound'),
            ('journal_id.company_id', '=', company.id),
            ('journal_id.active', '=', True),
        ], order='sequence, id', limit=1)

    @api.model
    def _hotel_setup_payment_modes(self):
        """Prépare les 4 modes de paiement de l'auberge (cahier des charges §8),
        pour chaque société ayant un plan comptable :
          - Espèces          -> journal Espèces
          - Virement / Chèque -> journal Banque
          - Carte bancaire   -> journal « Carte bancaire » (créé si absent)
        Idempotent : ne crée que ce qui manque, ne supprime rien."""
        Method = self.env['account.payment.method'].sudo()
        MethodLine = self.env['account.payment.method.line'].sudo()
        Journal = self.sudo()
        manual_in = Method.search(
            [('code', '=', 'manual'), ('payment_type', '=', 'inbound')], limit=1)
        # Mode « Chèque » du module payment_cheque_ref s'il est installé
        cheque_in = Method.search(
            [('code', '=', 'cheque_ref'), ('payment_type', '=', 'inbound')],
            limit=1) or manual_in
        if not manual_in:
            return

        def ensure_line(journal, mode, name, method):
            if not journal or self._hotel_get_payment_method_line(
                    mode, journal.company_id):
                return
            # Réutilise une ligne existante de la bonne méthode, encore libre
            line = journal.inbound_payment_method_line_ids.filtered(
                lambda l: l.payment_method_id == method and not l.hotel_payment_mode)[:1]
            if line:
                line.write({'hotel_payment_mode': mode, 'name': name})
            else:
                MethodLine.create({
                    'journal_id': journal.id,
                    'payment_method_id': method.id,
                    'name': name,
                    'hotel_payment_mode': mode,
                })

        for company in self.env['res.company'].sudo().search([]):
            if not company.chart_template:
                continue
            domain = [('company_id', '=', company.id)]
            cash = Journal.search(domain + [('type', '=', 'cash')], limit=1)
            card = Journal.search(domain + [
                ('type', '=', 'bank'),
                ('inbound_payment_method_line_ids.hotel_payment_mode', '=', 'card'),
            ], limit=1)
            bank = Journal.search(domain + [
                ('type', '=', 'bank'), ('id', '!=', card.id)], limit=1)

            ensure_line(cash, 'cash', "Espèces", manual_in)
            ensure_line(bank, 'transfer', "Virement", manual_in)
            ensure_line(bank, 'cheque', "Chèque", cheque_in)

            if not card and not self._hotel_get_payment_method_line('card', company):
                code = 'CARTE'
                if Journal.search_count(domain + [('code', '=', code)]):
                    code = 'CB'
                card = Journal.create({
                    'name': "Carte bancaire",
                    'code': code,
                    'type': 'bank',
                    'company_id': company.id,
                })
            ensure_line(card, 'card', "Carte bancaire", manual_in)
