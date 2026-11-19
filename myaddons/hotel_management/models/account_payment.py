import re
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Modes de paiement de l'auberge (cahier des charges §8)
HOTEL_PAYMENT_MODES = [
    ('cash', 'Espèces'),
    ('card', 'TPE'),
    ('transfer', 'Virement bancaire'),
    ('cheque', 'Chèque'),
]

# Cartes acceptées au TPE
HOTEL_CARD_TYPES = [
    ('cib', 'Carte CIB'),
    ('ccp', 'Carte CCP'),
    ('visa', 'Carte Visa'),
]


def hotel_card_digits(number):
    """Chiffres du numéro de carte saisi (espaces / tirets ignorés)."""
    return re.sub(r'[\s-]', '', number or '')


def hotel_mask_card_number(number):
    """Numéro masqué conservé en base : seuls les 4 derniers chiffres restent
    lisibles (on ne stocke jamais le numéro complet d'une carte)."""
    digits = hotel_card_digits(number)
    if not digits:
        return False
    if set(digits) <= {'*'} or '*' in digits:
        return number  # déjà masqué
    return '**** **** **** ' + digits[-4:]


def hotel_check_card(number, expiry):
    """Contrôle le numéro (13 à 19 chiffres) et la date d'expiration (MM/AA,
    non dépassée). Lève une ValidationError avec un message clair."""
    if number and '*' not in number:
        digits = hotel_card_digits(number)
        if not digits.isdigit() or not 13 <= len(digits) <= 19:
            raise ValidationError(_(
                "Numéro de carte invalide : saisissez de 13 à 19 chiffres."))
    if expiry:
        match = re.fullmatch(r'\s*(\d{1,2})\s*/\s*(\d{2}|\d{4})\s*', expiry)
        if not match or not 1 <= int(match.group(1)) <= 12:
            raise ValidationError(_(
                "Date d'expiration invalide : utilisez le format MM/AA (ex. 08/27)."))
        month, year = int(match.group(1)), int(match.group(2))
        year = year + 2000 if year < 100 else year
        today = date.today()
        if (year, month) < (today.year, today.month):
            raise ValidationError(_("La carte a expiré (%s).", expiry.strip()))


def hotel_format_expiry(expiry):
    """Normalise la date d'expiration au format MM/AA."""
    match = re.fullmatch(r'\s*(\d{1,2})\s*/\s*(\d{2}|\d{4})\s*', expiry or '')
    if not match:
        return expiry or False
    return '%02d/%s' % (int(match.group(1)), match.group(2)[-2:])


HOTEL_PAYMENT_KINDS = [
    ('deposit', 'Acompte'),
    ('payment', 'Paiement'),
    ('refund', 'Remboursement'),
]


class AccountPaymentMethodLine(models.Model):
    _inherit = 'account.payment.method.line'

    hotel_payment_mode = fields.Selection(
        HOTEL_PAYMENT_MODES, string="Mode (Auberge)",
        help="Mode de paiement proposé à la réception de l'auberge "
             "(Espèces, TPE, Virement, Chèque).")


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

    # Paiement par TPE : carte utilisée (le numéro est conservé masqué)
    hotel_card_type = fields.Selection(HOTEL_CARD_TYPES, string="Type de carte")
    hotel_card_last_name = fields.Char(string="Nom du titulaire")
    hotel_card_first_name = fields.Char(string="Prénom du titulaire")
    hotel_card_number = fields.Char(
        string="Numéro de la carte",
        help="Seuls les 4 derniers chiffres sont conservés.")
    hotel_card_expiry = fields.Char(
        string="Date d'expiration", size=7, help="Format MM/AA")
    # Paiement par virement ou par chèque
    hotel_bank_name = fields.Char(string="Banque")
    hotel_transfer_number = fields.Char(string="Numéro de virement")
    hotel_cheque_number = fields.Char(string="Numéro de chèque")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._hotel_normalize_card_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._hotel_normalize_card_vals(vals)
        return super().write(vals)

    @api.model
    def _hotel_normalize_card_vals(self, vals):
        if vals.get('hotel_card_number'):
            hotel_check_card(vals['hotel_card_number'], vals.get('hotel_card_expiry'))
            vals['hotel_card_number'] = hotel_mask_card_number(vals['hotel_card_number'])
        if vals.get('hotel_card_expiry'):
            vals['hotel_card_expiry'] = hotel_format_expiry(vals['hotel_card_expiry'])


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
    def _hotel_get_outbound_method_line(self, journal):
        """Ligne de mode de paiement sortant d'un journal (remboursements)."""
        return journal.outbound_payment_method_line_ids.sorted(
            lambda l: (l.payment_method_id.code != 'manual', l.sequence))[:1]

    @api.model
    def _hotel_setup_payment_modes(self):
        """Prépare les 4 modes de paiement de l'auberge (cahier des charges §8),
        pour chaque société ayant un plan comptable :
          - Espèces          -> journal Espèces
          - Virement / Chèque -> journal Banque
          - TPE              -> journal « TPE » (créé si absent)
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
                    'name': "TPE",
                    'code': code,
                    'type': 'bank',
                    'company_id': company.id,
                })
            ensure_line(card, 'card', "TPE", manual_in)
