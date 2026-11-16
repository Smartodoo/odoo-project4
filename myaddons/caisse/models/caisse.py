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
        'account.payment', 'caisse_session_id', string="Paiements en espèces",
        help="Tous les paiements en espèces rattachés à la caisse (clients et fournisseurs).")
    customer_payment_ids = fields.One2many(
        'account.payment', 'caisse_session_id', string="Paiements clients",
        domain=[('partner_type', '=', 'customer')])
    supplier_payment_ids = fields.One2many(
        'account.payment', 'caisse_session_id', string="Achats fournisseurs",
        domain=[('partner_type', '=', 'supplier'), ('caisse_kind', '!=', 'expense_note')])
    expense_note_payment_ids = fields.One2many(
        'account.payment', 'caisse_session_id', string="Notes de frais",
        domain=[('caisse_kind', '=', 'expense_note')])
    move_ids = fields.One2many(
        'caisse.move', 'session_id', string="Mouvements de caisse")

    total_cash_payments = fields.Monetary(
        string="Paiements clients (espèces)", compute='_compute_totals')
    total_supplier_payments = fields.Monetary(
        string="Achats fournisseurs (espèces)", compute='_compute_totals',
        help="Paiements fournisseurs en espèces sortis de la caisse "
             "(remboursements fournisseurs déduits).")
    total_expense_notes = fields.Monetary(
        string="Notes de frais (espèces)", compute='_compute_totals',
        help="Notes de frais payées en espèces par la caisse (payées par la "
             "société ou remboursées à l'employé).")
    total_in = fields.Monetary(string="Entrées", compute='_compute_totals')
    total_out = fields.Monetary(
        string="Sorties, dépenses et transferts", compute='_compute_totals')
    total_collected = fields.Monetary(
        string="Total encaissé", compute='_compute_totals',
        help="Paiements clients en espèces + entrées diverses.")
    total_spent = fields.Monetary(
        string="Total dépensé", compute='_compute_totals',
        help="Notes de frais + achats fournisseurs + sorties + transferts.")
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
                 'payment_ids.partner_type', 'payment_ids.caisse_kind',
                 'payment_ids.amount_company_currency_signed', 'move_ids.amount',
                 'move_ids.move_type', 'date_open', 'date_close')
    def _compute_totals(self):
        Payment = self.env['account.payment'].sudo()
        for rec in self:
            valid = rec._valid_payments(rec.sudo().payment_ids)
            cash = sum(valid.filtered(lambda p: p.partner_type != 'supplier').mapped(
                'amount_company_currency_signed'))
            # Paiement fournisseur : montant signé négatif (sortie) -> positif ici
            notes = valid.filtered(lambda p: p.caisse_kind == 'expense_note')
            expense_notes = -sum(notes.mapped('amount_company_currency_signed'))
            supplier = -sum((valid - notes).filtered(
                lambda p: p.partner_type == 'supplier').mapped('amount_company_currency_signed'))
            moves_in = sum(rec.move_ids.filtered(
                lambda m: m.move_type == 'in').mapped('amount'))
            moves_out = sum(rec.move_ids.filtered(
                lambda m: m.move_type != 'in').mapped('amount'))
            rec.total_cash_payments = cash
            rec.total_supplier_payments = supplier
            rec.total_expense_notes = expense_notes
            rec.total_in = moves_in
            rec.total_out = moves_out
            rec.total_collected = cash + moves_in
            rec.total_spent = moves_out + supplier + expense_notes
            rec.theoretical_balance = (rec.opening_balance + cash + moves_in
                                       - moves_out - supplier - expense_notes)
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
            # Encaissements clients uniquement (les achats ne sont pas des recettes)
            period |= rec.sudo().payment_ids.filtered(
                lambda p: p.partner_type != 'supplier' and p.caisse_kind != 'expense_note')
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

    # ------------------------------------------------------------------
    # Saisie rapide et accès au journal (formulaire de session)
    # ------------------------------------------------------------------
    journal_count = fields.Integer(
        string="Opérations", compute='_compute_journal_count')

    def _compute_journal_count(self):
        data = self.env['caisse.journal'].sudo()._read_group(
            [('session_id', 'in', self.ids)], ['session_id'], ['__count'])
        counts = {session.id: count for session, count in data}
        for rec in self:
            rec.journal_count = counts.get(rec.id, 0)

    def _action_new_move(self, move_type):
        self.ensure_one()
        if self.state != 'open':
            raise UserError(_("La caisse %s est fermée.", self.name))
        label = dict(CASH_MOVE_TYPES)[move_type]
        return {
            'type': 'ir.actions.act_window',
            'name': _("%(type)s — %(caisse)s", type=label, caisse=self.name),
            'res_model': 'caisse.move',
            'view_mode': 'form',
            'views': [(self.env.ref('caisse.view_caisse_move_form_quick').id, 'form')],
            'target': 'new',
            'context': {
                'default_session_id': self.id,
                'default_move_type': move_type,
            },
        }

    def action_new_in(self):
        return self._action_new_move('in')

    def action_new_out(self):
        return self._action_new_move('out')

    def action_new_transfer(self):
        return self._action_new_move('transfer')

    def action_view_journal(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('caisse.action_caisse_journal')
        action['domain'] = [('session_id', '=', self.id)]
        action['context'] = {'search_default_group_kind': 0}
        action['name'] = _("Journal — %s", self.name)
        return action

    # ------------------------------------------------------------------
    # Tableau de bord du responsable
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None):
        """Tout ce que le responsable doit voir d'un coup d'œil (cf. action
        client « caisse_dashboard »).
        date_from / date_to (« AAAA-MM-JJ », inclus) : période des statistiques
        (tuiles, alertes, graphique). Par défaut : du 1er du mois à aujourd'hui.
        La caisse ouverte et « Encaissé aujourd'hui » restent sur le jour même."""
        company = self.env.company
        currency = company.currency_id
        Session = self.sudo()
        Journal = self.env['caisse.journal'].sudo()
        Payment = self.env['account.payment'].sudo()
        today = fields.Date.context_today(self)
        date_from = fields.Date.to_date(date_from) or today.replace(day=1)
        date_to = fields.Date.to_date(date_to) or today
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        modes = dict(HOTEL_PAYMENT_MODES)

        def rnd(value):
            return currency.round(value or 0.0)

        # --- Caisse ouverte -------------------------------------------------
        current = Session._get_open_session(company)
        current_data = False
        if current:
            current_data = {
                'id': current.id,
                'name': current.name,
                'user': current.user_id.name,
                'date_open': fields.Datetime.to_string(
                    fields.Datetime.context_timestamp(self, current.date_open)),
                'opening': rnd(current.opening_balance),
                'cash_payments': rnd(current.total_cash_payments),
                'supplier_payments': rnd(current.total_supplier_payments),
                'expense_notes': rnd(current.total_expense_notes),
                'moves_out': rnd(current.total_out),
                'moves_in': rnd(current.total_in),
                'collected': rnd(current.total_collected),
                'spent': rnd(current.total_spent),
                'theoretical': rnd(current.theoretical_balance),
                'by_mode': [{'label': label, 'amount': rnd(amount)}
                            for label, amount in current.payments_by_mode()],
                'nb_ops': current.journal_count,
            }

        # --- Encaissements du jour, tous modes (paiements de l'auberge) -----
        today_payments = Payment.search([
            ('hotel_reservation_id', '!=', False),
            ('company_id', '=', company.id),
            ('state', 'in', ('paid', 'reconciled')),
            ('date', '=', today),
        ])
        today_by_mode = dict.fromkeys(modes, 0.0)
        for payment in today_payments:
            if payment.hotel_payment_mode in today_by_mode:
                today_by_mode[payment.hotel_payment_mode] += payment.amount_company_currency_signed
        today_spent = sum(Journal.search([
            ('company_id', '=', company.id), ('day', '=', today),
            ('category', 'in', ('expense', 'out')),
        ]).mapped('amount_out'))

        # --- Période choisie --------------------------------------------------
        month_lines = Journal.search([
            ('company_id', '=', company.id),
            ('day', '>=', date_from), ('day', '<=', date_to)])
        month_by_kind = {}
        month_by_category = {}
        for line in month_lines:
            month_by_kind[line.kind] = month_by_kind.get(line.kind, 0.0) + abs(line.amount)
            month_by_category[line.category] = (
                month_by_category.get(line.category, 0.0) + abs(line.amount))
        dt_from = fields.Datetime.to_datetime(date_from)
        dt_to = fields.Datetime.to_datetime(fields.Date.add(date_to, days=1))
        month_sessions = Session.search([
            ('company_id', '=', company.id),
            ('date_open', '>=', dt_from), ('date_open', '<', dt_to)])
        closed = month_sessions.filtered(lambda s: s.state == 'closed')
        gap_sessions = closed.filtered(
            lambda s: not currency.is_zero(s.difference))

        # --- Graphique de la période (espèces entrées / sorties) --------------
        # par jour jusqu'à 31 jours, sinon par mois
        nb_days = (date_to - date_from).days + 1
        by_month = nb_days > 31
        buckets = {}
        if by_month:
            cursor = date_from.replace(day=1)
            while cursor <= date_to:
                buckets[cursor] = {
                    'day': fields.Date.to_string(max(cursor, date_from)),
                    'day_to': fields.Date.to_string(min(
                        fields.Date.end_of(cursor, 'month'), date_to)),
                    'label': cursor.strftime('%m/%Y'), 'in': 0.0, 'out': 0.0}
                cursor = fields.Date.add(cursor, months=1)
        else:
            for offset in range(nb_days):
                day = fields.Date.add(date_from, days=offset)
                buckets[day] = {
                    'day': fields.Date.to_string(day), 'day_to': fields.Date.to_string(day),
                    'label': day.strftime('%d/%m'), 'in': 0.0, 'out': 0.0}
        for line in month_lines:
            key = line.day.replace(day=1) if by_month else line.day
            if key in buckets:
                buckets[key]['in'] += line.amount_in
                buckets[key]['out'] += line.amount_out
        days = [dict(b, **{'in': rnd(b['in']), 'out': rnd(b['out'])})
                for _k, b in sorted(buckets.items())]
        max_day = max([max(d['in'], d['out']) for d in days] + [1])

        # --- Dernières opérations et dernières caisses fermées --------------
        kinds = dict(self.env['caisse.journal']._fields['kind'].selection)
        recent = [{
            'id': line.id,
            'date': fields.Datetime.to_string(
                fields.Datetime.context_timestamp(self, line.date)) if line.date else '',
            'kind': line.kind,
            'kind_label': kinds.get(line.kind, ''),
            'label': line.label or '',
            'partner': line.partner_id.display_name or '',
            'amount': rnd(line.amount),
            'session': line.session_id.name or '',
            'has_attachment': line.has_attachment,
        } for line in Journal.search([('company_id', '=', company.id)], limit=10)]

        last_closed = [{
            'id': s.id,
            'name': s.name,
            'user': s.user_id.name,
            'date_close': fields.Datetime.to_string(
                fields.Datetime.context_timestamp(self, s.date_close)) if s.date_close else '',
            'theoretical': rnd(s.theoretical_balance),
            'counted': rnd(s.closing_balance),
            'difference': rnd(s.difference),
        } for s in Session.search([
            ('company_id', '=', company.id), ('state', '=', 'closed')],
            order='date_close desc', limit=5)]

        missing_proof = self.env['caisse.move'].sudo().search_count([
            ('company_id', '=', company.id),
            ('move_type', '!=', 'in'),
            ('attachment', '=', False),
            ('date', '>=', dt_from), ('date', '<', dt_to),
        ])

        return {
            'currency_symbol': currency.symbol or '',
            'is_manager': self.env.user.has_group('caisse.group_caisse_manager'),
            'current': current_data,
            'today': {
                'by_mode': [{'mode': m, 'label': modes[m], 'amount': rnd(today_by_mode[m])}
                            for m in modes],
                'total': rnd(sum(today_by_mode.values())),
                'spent': rnd(today_spent),
            },
            'month': {
                'label': date_from.strftime('%d/%m/%Y') + ' – ' + date_to.strftime('%d/%m/%Y'),
                'start': fields.Date.to_string(date_from),
                'end': fields.Date.to_string(date_to),
                'by_month': by_month,
                'payments': rnd(month_by_kind.get('payment', 0.0)),
                'refunds': rnd(month_by_kind.get('refund', 0.0)),
                'in': rnd(month_by_kind.get('in', 0.0)),
                # Dépenses = notes de frais (+ anciennes dépenses saisies) et achats
                'expense': rnd(month_by_kind.get('expense', 0.0)
                               + month_by_kind.get('expense_note', 0.0)),
                'total_in': rnd(month_by_category.get('in', 0.0)),
                'total_expense': rnd(month_by_category.get('expense', 0.0)),
                'total_out': rnd(month_by_category.get('out', 0.0)),
                'out': rnd(month_by_kind.get('out', 0.0)),
                'transfer': rnd(month_by_kind.get('transfer', 0.0)),
                'purchase': rnd(month_by_kind.get('purchase', 0.0)
                                - month_by_kind.get('purchase_refund', 0.0)),
                'sessions': len(month_sessions),
                'gap_sessions': len(gap_sessions),
                'gap_session_ids': gap_sessions.ids,
                'gap_total': rnd(sum(closed.mapped('difference'))),
                'missing_proof': missing_proof,
            },
            'today_iso': fields.Date.to_string(today),
            'days': days,
            'max_day': max_day,
            'recent': recent,
            'last_closed': last_closed,
        }

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

    @api.constrains('move_type', 'partner_id')
    def _check_out_beneficiary(self):
        for rec in self:
            if rec.move_type == 'out' and not rec.partner_id:
                raise ValidationError(_(
                    "Une sortie d'argent doit indiquer à qui l'argent a été remis "
                    "(champ « Bénéficiaire »)."))

    @api.constrains('session_id', 'amount', 'move_type')
    def _check_session_open(self):
        for rec in self:
            if rec.session_id.state != 'open':
                raise ValidationError(_(
                    "La caisse %s est fermée : impossible d'y enregistrer un mouvement.",
                    rec.session_id.name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('session_id'):
                session = self.env['caisse.session']._get_open_session()
                if not session:
                    raise UserError(_(
                        "Aucune caisse n'est ouverte : ouvrez la caisse du jour "
                        "(menu Caisse > Caisse du jour) avant d'enregistrer une "
                        "entrée, une dépense, une sortie ou un transfert."))
                vals['session_id'] = session.id
        return super().create(vals_list)

    def write(self, vals):
        # Le type est fixé à la création (menu ou bouton) : il ne change jamais.
        if 'move_type' in vals and any(m.move_type != vals['move_type'] for m in self):
            raise UserError(_(
                "Le type d'un mouvement de caisse ne peut pas être modifié : "
                "supprimez-le et saisissez-le depuis le bon menu."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_open(self):
        for rec in self:
            if rec.session_id.state != 'open':
                raise UserError(_(
                    "Ce mouvement appartient à une caisse fermée et ne peut pas être supprimé."))
