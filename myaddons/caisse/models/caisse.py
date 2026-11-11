from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from odoo.addons.hotel_management.models.account_payment import HOTEL_PAYMENT_MODES

CASH_MOVE_TYPES = [
    ('in', 'Entrée'),
    ('out', 'Sortie'),
    ('expense', 'Dépense'),
    ('transfer', 'Transfert'),
]


class CaisseSession(models.Model):
    """Session de caisse (cahier des charges §9) : ouverture avec
    un fond de caisse, encaissements clients en espèces, entrées / sorties /
    dépenses / transferts justifiés, fermeture avec comptage et écart."""
    _name = 'caisse.session'
    _description = "Session de caisse"
    _order = 'date_open desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=lambda self: _('Nouveau'))
    user_id = fields.Many2one(
        'res.users', string="Caissier", required=True, tracking=True,
        default=lambda self: self.env.user)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection([
        ('open', 'Ouverte'),
        ('closed', 'Fermée'),
    ], string="État", default='open', required=True, tracking=True, copy=False)
    date_open = fields.Datetime(
        string="Ouverture", required=True, default=fields.Datetime.now, readonly=True)
    date_close = fields.Datetime(string="Fermeture", readonly=True, copy=False)
    opening_balance = fields.Monetary(
        string="Fond de caisse (ouverture)", tracking=True,
        help="Espèces présentes dans la caisse à l'ouverture.")
    closing_balance = fields.Monetary(
        string="Espèces comptées (fermeture)", tracking=True, copy=False,
        help="Montant réellement compté dans la caisse à la fermeture.")
    note = fields.Text(string="Observations")

    payment_ids = fields.One2many(
        'account.payment', 'caisse_session_id', string="Paiements clients")
    move_ids = fields.One2many(
        'caisse.move', 'session_id', string="Mouvements de caisse")

    total_cash_payments = fields.Monetary(
        string="Paiements clients (espèces)", compute='_compute_totals')
    total_in = fields.Monetary(string="Entrées", compute='_compute_totals')
    total_out = fields.Monetary(
        string="Sorties, dépenses et transferts", compute='_compute_totals')
    total_collected = fields.Monetary(
        string="Total encaissé", compute='_compute_totals',
        help="Paiements clients en espèces + entrées diverses.")
    total_spent = fields.Monetary(
        string="Total dépensé", compute='_compute_totals',
        help="Sorties + dépenses + transferts.")
    theoretical_balance = fields.Monetary(
        string="Solde théorique", compute='_compute_totals',
        help="Fond de caisse + total encaissé - total dépensé.")
    difference = fields.Monetary(
        string="Écart de caisse", compute='_compute_totals',
        help="Espèces comptées - solde théorique (négatif = manque).")
    amount_card = fields.Monetary(string="Carte bancaire", compute='_compute_totals')
    amount_transfer = fields.Monetary(string="Virement", compute='_compute_totals')
    amount_cheque = fields.Monetary(string="Chèque", compute='_compute_totals')
    period_payment_ids = fields.Many2many(
        'account.payment', string="Tous les paiements de la période",
        compute='_compute_totals',
        help="Paiements de l'auberge (tous modes) encaissés pendant la session.")

    _one_open_per_company = models.UniqueIndex(
        '(company_id) WHERE state = \'open\'',
        "Une caisse est déjà ouverte : fermez-la avant d'en ouvrir une nouvelle.",
    )

    def _valid_payments(self, payments):
        return payments.filtered(lambda p: p.state in ('paid', 'reconciled'))

    @api.depends('opening_balance', 'closing_balance', 'payment_ids.state',
                 'payment_ids.amount_company_currency_signed', 'move_ids.amount',
                 'move_ids.move_type', 'date_open', 'date_close')
    def _compute_totals(self):
        Payment = self.env['account.payment'].sudo()
        for rec in self:
            cash = sum(rec._valid_payments(rec.sudo().payment_ids).mapped(
                'amount_company_currency_signed'))
            moves_in = sum(rec.move_ids.filtered(
                lambda m: m.move_type == 'in').mapped('amount'))
            moves_out = sum(rec.move_ids.filtered(
                lambda m: m.move_type != 'in').mapped('amount'))
            rec.total_cash_payments = cash
            rec.total_in = moves_in
            rec.total_out = moves_out
            rec.total_collected = cash + moves_in
            rec.total_spent = moves_out
            rec.theoretical_balance = rec.opening_balance + cash + moves_in - moves_out
            rec.difference = (rec.closing_balance - rec.theoretical_balance
                              if rec.state == 'closed' else 0.0)
            # Paiements par mode encaissés pendant la session (rapport de caisse)
            domain = [
                ('hotel_reservation_id', '!=', False),
                ('company_id', '=', rec.company_id.id),
                ('state', 'in', ('paid', 'reconciled')),
            ]
            if rec.date_open:
                domain.append(('date', '>=', fields.Date.to_date(rec.date_open)))
            if rec.date_close:
                domain.append(('date', '<=', fields.Date.to_date(rec.date_close)))
            period = Payment.search(domain) if rec.id else Payment
            period |= rec.sudo().payment_ids
            rec.period_payment_ids = period
            by_mode = {}
            for payment in rec._valid_payments(period):
                mode = payment.hotel_payment_mode or 'other'
                by_mode[mode] = by_mode.get(mode, 0.0) + payment.amount_company_currency_signed
            rec.amount_card = by_mode.get('card', 0.0)
            rec.amount_transfer = by_mode.get('transfer', 0.0)
            rec.amount_cheque = by_mode.get('cheque', 0.0)

    def payments_by_mode(self):
        """[(libellé, montant)] pour le rapport « État de caisse »."""
        self.ensure_one()
        totals = dict.fromkeys([m for m, _l in HOTEL_PAYMENT_MODES], 0.0)
        for payment in self._valid_payments(self.period_payment_ids):
            mode = payment.hotel_payment_mode
            if mode in totals:
                totals[mode] += payment.amount_company_currency_signed
        return [(label, totals[mode]) for mode, label in HOTEL_PAYMENT_MODES]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'caisse.session') or _('Nouveau')
        return super().create(vals_list)

    @api.constrains('opening_balance', 'closing_balance')
    def _check_balances(self):
        for rec in self:
            if rec.opening_balance < 0 or rec.closing_balance < 0:
                raise ValidationError(_("Les montants de caisse ne peuvent pas être négatifs."))

    def action_close(self):
        for rec in self:
            if rec.state != 'open':
                raise UserError(_("La caisse %s est déjà fermée.", rec.name))
            rec.write({'state': 'closed', 'date_close': fields.Datetime.now()})
            rec.message_post(body=_(
                "Caisse fermée. Solde théorique : %(theo)s — compté : %(counted)s — "
                "écart : %(gap)s.",
                theo=rec.theoretical_balance, counted=rec.closing_balance,
                gap=rec.difference))

    def action_reopen(self):
        for rec in self:
            if not self.env.user.has_group('caisse.group_caisse_manager'):
                raise UserError(_("Seul un responsable peut rouvrir une caisse."))
            rec.write({'state': 'open', 'date_close': False})

    @api.ondelete(at_uninstall=False)
    def _unlink_only_empty(self):
        for rec in self:
            if rec.payment_ids or rec.move_ids:
                raise UserError(_(
                    "La caisse %s contient des opérations et ne peut pas être supprimée.",
                    rec.name))

    @api.model
    def _get_open_session(self, company=None):
        company = company or self.env.company
        return self.sudo().search([
            ('state', '=', 'open'), ('company_id', '=', company.id)], limit=1)

    @api.model
    def action_open_current(self):
        """Menu « Caisse du jour » : ouvre la session en cours, ou propose
        d'en ouvrir une nouvelle."""
        session = self._get_open_session()
        action = {
            'type': 'ir.actions.act_window',
            'name': _("Caisse"),
            'res_model': 'caisse.session',
            'view_mode': 'form',
            'target': 'current',
        }
        if session:
            action['res_id'] = session.id
        return action


class CaisseMove(models.Model):
    """Mouvement de caisse hors paiement client : entrée, sortie, dépense ou
    transfert (vers la banque, le coffre…), toujours justifié."""
    _name = 'caisse.move'
    _description = "Mouvement de caisse"
    _order = 'date desc, id desc'

    session_id = fields.Many2one(
        'caisse.session', string="Caisse", required=True, ondelete='restrict',
        index=True, domain="[('state', '=', 'open')]",
        default=lambda self: self.env['caisse.session']._get_open_session())
    date = fields.Datetime(string="Date", required=True, default=fields.Datetime.now)
    move_type = fields.Selection(
        CASH_MOVE_TYPES, string="Type", required=True, default='expense')
    amount = fields.Monetary(string="Montant", required=True)
    signed_amount = fields.Monetary(
        string="Montant signé", compute='_compute_signed_amount', store=True)
    reason = fields.Char(string="Justification", required=True,
                         help="Motif du mouvement (obligatoire).")
    partner_id = fields.Many2one('res.partner', string="Tiers")
    reference = fields.Char(string="N° de pièce / reçu")
    destination = fields.Char(
        string="Destination du transfert", help="Banque, coffre, autre caisse…")
    attachment = fields.Binary(string="Justificatif", attachment=True)
    attachment_name = fields.Char(string="Nom du justificatif")
    user_id = fields.Many2one(
        'res.users', string="Saisi par", default=lambda self: self.env.user, readonly=True)
    company_id = fields.Many2one(related='session_id.company_id', store=True)
    currency_id = fields.Many2one(related='session_id.currency_id')

    @api.depends('amount', 'move_type')
    def _compute_signed_amount(self):
        for rec in self:
            rec.signed_amount = rec.amount if rec.move_type == 'in' else -rec.amount

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("Le montant d'un mouvement de caisse doit être positif."))

    @api.constrains('session_id', 'amount', 'move_type')
    def _check_session_open(self):
        for rec in self:
            if rec.session_id.state != 'open':
                raise ValidationError(_(
                    "La caisse %s est fermée : impossible d'y enregistrer un mouvement.",
                    rec.session_id.name))

    @api.ondelete(at_uninstall=False)
    def _unlink_only_open(self):
        for rec in self:
            if rec.session_id.state != 'open':
                raise UserError(_(
                    "Ce mouvement appartient à une caisse fermée et ne peut pas être supprimé."))
