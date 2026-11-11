from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class HotelReservation(models.Model):
    _name = 'hotel.reservation'
    _description = "Réservation"
    _order = 'checkin desc, id desc'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=lambda self: _('Nouveau'))
    user_id = fields.Many2one(
        'res.users', string="Responsable", tracking=True,
        default=lambda self: self.env.user,
        help="Employé de la réception qui suit la réservation : il reçoit les "
             "alertes (arrivée, départ, paiement en retard).")
    service_ids = fields.One2many(
        'hotel.reservation.service', 'reservation_id',
        string="Consommations & services", copy=False)
    # Remise sur le séjour (cahier des charges §5)
    discount_type = fields.Selection([
        ('percent', 'Pourcentage'),
        ('amount', 'Montant'),
    ], string="Type de remise", default='percent', required=True)
    discount_value = fields.Float(
        string="Remise", digits=(16, 2),
        help="Pourcentage (0-100) ou montant, selon le type de remise. "
             "Proposée automatiquement à partir de la remise du client.")
    amount_rooms = fields.Monetary(
        string="Hébergement", compute='_compute_amounts', store=True)
    amount_services = fields.Monetary(
        string="Montant consommations", compute='_compute_amounts', store=True)
    amount_gross = fields.Monetary(
        string="Montant avant remise", compute='_compute_amounts', store=True)
    amount_discount = fields.Monetary(
        string="Montant de la remise", compute='_compute_amounts', store=True)
    amount_untaxed = fields.Monetary(
        string="Total HT", compute='_compute_amounts', store=True)
    amount_tax = fields.Monetary(
        string="Taxes", compute='_compute_amounts', store=True)

    partner_id = fields.Many2one(
        'res.partner', string="Client", required=True, tracking=True)
    # Coordonnées et pièce d'identité du client, modifiables depuis la réservation
    partner_last_name = fields.Char(
        related='partner_id.hotel_last_name', readonly=False, string="Nom")
    partner_first_name = fields.Char(
        related='partner_id.hotel_first_name', readonly=False, string="Prénom")
    partner_phone = fields.Char(
        related='partner_id.phone', readonly=False, string="Téléphone")
    partner_street = fields.Char(
        related='partner_id.street', readonly=False, string="Adresse")
    partner_city = fields.Char(
        related='partner_id.city', readonly=False, string="Ville")
    partner_id_type = fields.Selection(
        related='partner_id.hotel_id_type', readonly=False)
    partner_id_number = fields.Char(
        related='partner_id.hotel_id_number', readonly=False)
    partner_birthdate = fields.Date(
        related='partner_id.hotel_birthdate', readonly=False)
    partner_id_document = fields.Binary(
        related='partner_id.hotel_id_document', readonly=False,
        string="Scan pièce d'identité")
    partner_id_document_name = fields.Char(
        related='partner_id.hotel_id_document_name', readonly=False)
    deposit_requested = fields.Monetary(
        string="Acompte demandé", compute='_compute_deposit_requested',
        help="Acompte demandé au client (pourcentage défini dans les paramètres).")
    checkin = fields.Date(
        string="Arrivée", required=True, tracking=True,
        default=fields.Date.context_today)
    checkout = fields.Date(string="Départ", required=True, tracking=True)
    nights = fields.Integer(
        string="Nuits", compute='_compute_nights', store=True, aggregator='avg',
        help="Nombre de nuits. Dans les analyses : durée moyenne des séjours.")
    adults = fields.Integer(string="Adultes", default=1)
    children = fields.Integer(string="Enfants", default=0)
    guest_count = fields.Integer(
        string="Personnes", compute='_compute_guest_count', store=True)
    line_ids = fields.One2many(
        'hotel.reservation.line', 'reservation_id', string="Chambres", copy=True)
    room_count = fields.Integer(
        string="Nb chambres", compute='_compute_amounts', store=True)
    places = fields.Integer(
        string="Places réservées", compute='_compute_places',
        help="Lits réservés, ou capacité des chambres louées entières.")
    amount_total = fields.Monetary(
        string="Total séjour", compute='_compute_amounts', store=True, tracking=True)
    # Paiements réels (account.payment) rattachés à la réservation :
    # acomptes encaissés avant la facture et règlements du séjour.
    payment_ids = fields.One2many(
        'account.payment', 'hotel_reservation_id', string="Paiements")
    payment_count = fields.Integer(
        string="Nb paiements", compute='_compute_payment_count')
    deposit_amount = fields.Monetary(
        string="Acompte versé", compute='_compute_payment_amounts', store=True,
        tracking=True,
        help="Somme des acomptes réellement encaissés (paiements validés de "
             "type « Acompte »). Déduits automatiquement de la facture.")
    amount_paid = fields.Monetary(
        string="Payé", compute='_compute_payment_amounts', store=True,
        help="Total réellement encaissé : acomptes + paiements, "
             "moins les remboursements.")
    amount_due = fields.Monetary(
        string="Reste à payer", compute='_compute_payment_amounts', store=True)
    invoice_ids = fields.One2many(
        'account.move', 'hotel_reservation_id', string="Factures",
        domain=[('move_type', 'in', ('out_invoice', 'out_refund'))])
    invoice_count = fields.Integer(
        string="Nb factures", compute='_compute_invoice_count')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)
    source = fields.Selection([
        ('direct', 'Direct'),
        ('phone', 'Téléphone'),
        ('website', 'Site web'),
        ('booking', 'Booking / plateforme en ligne'),
        ('agency', 'Agence'),
        ('walkin', 'Sans réservation'),
        ('other', 'Autre'),
    ], string="Source", default='direct')
    booking_type = fields.Selection([
        ('room', 'Par chambre'),
        ('bed', 'Par lit'),
    ], string="Type de location", default='room', required=True, tracking=True,
        help="Par chambre : chaque chambre réservée est prise en entier.\n"
             "Par lit : on sélectionne les lits disponibles de chaque chambre.")
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('confirmed', 'Confirmée'),
        ('checkin', 'Enregistrée'),
        ('checkout', 'Terminée'),
        ('cancel', 'Annulée'),
    ], string="État", default='draft', tracking=True, copy=False)
    note = fields.Text(string="Notes")

    @api.depends('checkin', 'checkout')
    def _compute_nights(self):
        for rec in self:
            if rec.checkin and rec.checkout and rec.checkout > rec.checkin:
                rec.nights = (rec.checkout - rec.checkin).days
            else:
                rec.nights = 0

    @api.depends('adults', 'children')
    def _compute_guest_count(self):
        for rec in self:
            rec.guest_count = (rec.adults or 0) + (rec.children or 0)

    @api.depends('amount_total', 'company_id.hotel_deposit_percent')
    def _compute_deposit_requested(self):
        for rec in self:
            pct = rec.company_id.hotel_deposit_percent or 0.0
            amount = rec.amount_total * pct / 100.0
            rec.deposit_requested = rec.currency_id.round(amount) if rec.currency_id else amount

    def _hotel_priced_items(self):
        """[(produit, libellé, quantité, prix unitaire, montant)] du séjour :
        une ligne par chambre (produit « Nuitée ») et une par consommation."""
        self.ensure_one()
        night = self.env['product.product']._hotel_night_product()
        items = []
        for line in self.line_ids:
            items.append((night, line._invoice_label(), line.nights or 1,
                          line.price_unit, line.price_subtotal))
        for service in self.service_ids:
            items.append((service.product_id, service.name, service.quantity,
                          service.price_unit, service.price_subtotal))
        return items

    def _hotel_taxes(self, product):
        self.ensure_one()
        if not product:
            return self.env['account.tax']
        return product.sudo().taxes_id._filter_taxes_by_company(self.company_id)

    def _hotel_discount_amount(self, gross):
        self.ensure_one()
        value = max(self.discount_value or 0.0, 0.0)
        if self.discount_type == 'percent':
            discount = gross * min(value, 100.0) / 100.0
        else:
            discount = min(value, gross)
        return self.currency_id.round(discount) if self.currency_id else discount

    def _hotel_document_lines(self):
        """Lignes du séjour telles qu'elles figurent sur la facture :
        [(produit, libellé, quantité, prix unitaire, taxes)] — une par chambre,
        une par consommation, puis une ligne « Remise » (négative) par groupe
        de taxes, au prorata. Le total de la réservation et celui de la
        facture sont ainsi calculés exactement de la même façon."""
        self.ensure_one()
        lines = []
        groups = {}
        for product, label, qty, price, amount in self._hotel_priced_items():
            taxes = self._hotel_taxes(product)
            lines.append((product, label, qty, price, taxes))
            key = tuple(sorted(taxes.ids))
            groups.setdefault(key, [taxes, 0.0])[1] += amount
        gross = sum(amount for _taxes, amount in groups.values())
        discount = self._hotel_discount_amount(gross) if gross else 0.0
        if discount:
            if self.discount_type == 'percent':
                label = _("Remise %s %%", ('%g' % self.discount_value))
            else:
                label = _("Remise")
            remaining = discount
            items = [g for g in groups.values() if g[1]]
            for index, (taxes, amount) in enumerate(items):
                if index == len(items) - 1:
                    share = remaining
                else:
                    share = discount * amount / gross
                    share = self.currency_id.round(share) if self.currency_id else share
                remaining -= share
                if share:
                    lines.append((False, label, 1.0, -share, taxes))
        return lines

    @api.depends('line_ids.price_subtotal', 'service_ids.price_subtotal',
                 'service_ids.product_id', 'discount_type', 'discount_value')
    def _compute_amounts(self):
        for rec in self:
            rooms = sum(rec.line_ids.mapped('price_subtotal'))
            services = sum(rec.service_ids.mapped('price_subtotal'))
            untaxed = total = 0.0
            # Taxes ligne par ligne, comme sur la facture (arrondi par ligne)
            for product, _label, qty, price, taxes in rec._hotel_document_lines():
                amount = qty * price
                if taxes:
                    res = taxes.compute_all(
                        price, currency=rec.currency_id, quantity=qty,
                        product=product or None, partner=rec.partner_id)
                    untaxed += res['total_excluded']
                    total += res['total_included']
                else:
                    amount = rec.currency_id.round(amount) if rec.currency_id else amount
                    untaxed += amount
                    total += amount
            rec.amount_rooms = rooms
            rec.amount_services = services
            rec.amount_gross = rooms + services
            rec.amount_discount = rec._hotel_discount_amount(rooms + services) \
                if rooms + services else 0.0
            rec.amount_untaxed = untaxed
            rec.amount_tax = total - untaxed
            rec.amount_total = total
            rec.room_count = len(rec.line_ids)

    @api.constrains('discount_type', 'discount_value')
    def _check_discount(self):
        for rec in self:
            if rec.discount_value < 0:
                raise ValidationError(_("La remise ne peut pas être négative."))
            if rec.discount_type == 'percent' and rec.discount_value > 100:
                raise ValidationError(_("Une remise en pourcentage ne peut pas dépasser 100 %."))

    @api.onchange('partner_id')
    def _onchange_partner_id_hotel(self):
        """Remise et tarifs spéciaux du client appliqués à la réservation."""
        if self.partner_id and self.partner_id.hotel_discount and not self.discount_value:
            self.discount_type = 'percent'
            self.discount_value = self.partner_id.hotel_discount
        for line in self.line_ids:
            line._apply_price()

    @api.onchange('checkin', 'checkout')
    def _onchange_dates_reprice(self):
        """Nouvelles dates : prix recalculés (tarifs saisonniers nuit par nuit)."""
        for line in self.line_ids:
            line._apply_price()

    def _compute_access_url(self):
        super()._compute_access_url()
        for rec in self:
            rec.access_url = '/my/reservation/%s' % rec.id

    @api.depends('line_ids.booking_type', 'line_ids.bed_ids',
                 'line_ids.room_id.capacity')
    def _compute_places(self):
        for rec in self:
            rec.places = sum(line._get_places() for line in rec.line_ids)

    def _check_guest_places(self):
        """Il faut au moins un lit (ou une place) par personne."""
        for rec in self:
            if rec.guest_count > rec.places:
                raise UserError(_(
                    "La réservation %(name)s compte %(guests)s personne(s) mais "
                    "seulement %(places)s place(s) réservée(s).\n\n"
                    "Ajoutez des lits ou une chambre, ou corrigez le nombre "
                    "d'adultes / d'enfants.",
                    name=rec.name, guests=rec.guest_count, places=rec.places))

    @api.depends('amount_total', 'payment_ids.state',
                 'payment_ids.amount_company_currency_signed',
                 'payment_ids.hotel_payment_kind')
    def _compute_payment_amounts(self):
        # sudo : la réception voit les montants sans droits comptables
        for rec in self:
            posted = rec.sudo().payment_ids.filtered(lambda p: p.state in ('paid', 'reconciled'))  # Odoo 18+ : plus d'état 'posted'
            # Montant signé : + pour un encaissement, - pour un remboursement
            rec.amount_paid = sum(posted.mapped('amount_company_currency_signed'))
            rec.deposit_amount = sum(posted.filtered(
                lambda p: p.hotel_payment_kind == 'deposit'
                and p.payment_type == 'inbound'
            ).mapped('amount_company_currency_signed'))
            rec.amount_due = rec.amount_total - rec.amount_paid

    def _compute_payment_count(self):
        for rec in self:
            rec.payment_count = len(rec.sudo().payment_ids)

    def _hotel_reconcile_payments(self):
        """Lettre les encaissements de la réservation (acomptes, paiements)
        encore ouverts avec ses factures validées non soldées : l'acompte est
        ainsi déduit de la facture, qui n'affiche plus que le reste dû."""
        for rec in self.sudo():
            invoices = rec.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
                and m.payment_state in ('not_paid', 'partial'))
            if not invoices:
                continue
            payments = rec.payment_ids.filtered(
                lambda p: p.state in ('paid', 'reconciled') and p.payment_type == 'inbound')
            for invoice in invoices.sorted('invoice_date'):
                receivable = invoice.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable'
                ).account_id
                open_lines = payments.move_id.line_ids.filtered(
                    lambda l: l.account_id in receivable
                    and not l.reconciled and l.credit > 0)
                for line in open_lines:
                    if invoice.payment_state not in ('not_paid', 'partial'):
                        break
                    invoice.js_assign_outstanding_line(line.id)

    def action_register_hotel_payment(self):
        """Ouvre la fenêtre « Encaisser » (acompte ou paiement)."""
        self.ensure_one()
        if self.state == 'cancel' and not self.env.context.get('hotel_refund'):
            raise UserError(_("Impossible d'encaisser sur une réservation annulée."))
        if not self.partner_id:
            raise UserError(_("Renseignez le client avant d'encaisser."))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Encaisser — %s", self.name),
            'res_model': 'hotel.reservation.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_reservation_id': self.id},
        }

    def action_refund_hotel_payment(self):
        """Ouvre la fenêtre de remboursement (paiement sortant)."""
        self.ensure_one()
        if self.amount_paid <= 0:
            raise UserError(_("Aucun montant encaissé à rembourser sur %s.", self.name))
        action = self.with_context(hotel_refund=True).action_register_hotel_payment()
        action['name'] = _("Rembourser — %s", self.name)
        action['context'] = dict(action['context'], hotel_refund=True)
        return action

    def action_view_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Paiements — %s", self.name),
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('hotel_reservation_id', '=', self.id)],
            'context': {'create': False},
        }

    @api.constrains('deposit_amount', 'amount_total')
    def _check_deposit_not_above_total(self):
        for rec in self:
            # On ne contrôle que lorsqu'un total est connu (lignes saisies) :
            # un acompte encaissé avant d'ajouter les chambres reste permis.
            if rec.amount_total and rec.deposit_amount > rec.amount_total + 0.01:
                raise ValidationError(_(
                    "L'acompte (%(deposit)s) ne peut pas dépasser le total du "
                    "séjour (%(total)s).",
                    deposit=rec.deposit_amount, total=rec.amount_total))

    @api.constrains('adults', 'children')
    def _check_guest_counts(self):
        for rec in self:
            if (rec.adults or 0) < 1:
                raise ValidationError(_(
                    "Une réservation doit compter au moins un adulte."))
            if (rec.children or 0) < 0:
                raise ValidationError(_(
                    "Le nombre d'enfants ne peut pas être négatif."))

    @api.constrains('state', 'checkin', 'checkout', 'line_ids', 'adults', 'children')
    def _check_booking_integrity(self):
        """Toute modification d'une réservation déjà confirmée ou enregistrée
        est revalidée : places suffisantes et aucune surréservation. Sans cela,
        changer les dates ou les chambres d'une réservation confirmée pouvait
        créer un conflit sans alerte."""
        for rec in self:
            if rec.state in ('confirmed', 'checkin'):
                rec._check_guest_places()
                rec._check_availability()

    @api.onchange('booking_type')
    def _onchange_booking_type(self):
        """Le type de location est choisi sur la réservation : on l'applique à
        chaque ligne (chambre entière = tous les lits ; par lit = sélection)."""
        for line in self.line_ids:
            line._apply_booking_type()

    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    def _get_income_account(self):
        Account = self.env['account.account']
        account = Account.search([
            ('account_type', '=', 'income'),
            ('company_ids', 'in', self.company_id.id),  # Odoo 18+ : comptes multi-sociétés
        ], limit=1)
        if not account:
            account = Account.search([('account_type', '=', 'income')], limit=1)
        return account

    def action_create_invoice(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Renseignez le client avant de facturer."))
        if not self.line_ids:
            raise UserError(_("Rien à facturer sur ce séjour."))
        existing = self.invoice_ids.filtered(lambda m: m.state != 'cancel')
        if existing:
            raise UserError(_(
                "Une facture existe déjà pour la réservation %(name)s : %(inv)s.\n\n"
                "Utilisez le bouton « Factures » pour la consulter, ou annulez-la "
                "avant d'en créer une nouvelle.",
                name=self.name,
                inv=', '.join(existing.mapped('display_name'))))
        move = self._hotel_create_invoice()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Facture"),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _hotel_create_invoice(self):
        """Facture client du séjour (cahier des charges §7) : une ligne par
        chambre (produit « Nuitée » × nuits) et par consommation / service,
        puis la remise du séjour (ligne négative), taxes des produits."""
        self.ensure_one()
        income = self._get_income_account()
        move_lines = []
        for product, label, qty, price, taxes in self._hotel_document_lines():
            vals = {
                'name': label,
                'quantity': qty,
                'price_unit': price,
                'tax_ids': [(6, 0, taxes.ids)],
            }
            if product:
                vals['product_id'] = product.id
            elif income:
                vals['account_id'] = income.id
            move_lines.append((0, 0, vals))
        return self.env['account.move'].sudo().create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_origin': self.name,
            'invoice_date': fields.Date.context_today(self),
            'hotel_reservation_id': self.id,
            'invoice_line_ids': move_lines,
        })

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Factures"),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            # Factures et avoirs seulement : les écritures des paiements
            # portent aussi la réservation (bouton « Paiements »).
            'domain': [('hotel_reservation_id', '=', self.id),
                       ('move_type', 'in', ('out_invoice', 'out_refund'))],
        }

    def action_send_confirmation(self):
        self.ensure_one()
        template = self.env.ref(
            'hotel_management.mail_template_reservation_confirmation',
            raise_if_not_found=False)
        if template and self.partner_id.email:
            template.sudo().send_mail(self.id, force_send=False)
        return True

    @api.constrains('checkin', 'checkout')
    def _check_dates(self):
        for rec in self:
            if rec.checkin and rec.checkout and rec.checkout <= rec.checkin:
                raise ValidationError(
                    _("La date de départ doit être postérieure à la date d'arrivée."))

    def _check_availability(self):
        for rec in self:
            for line in rec.line_ids:
                if not line.room_id:
                    continue
                if line.booking_type == 'bed' and line.bed_ids:
                    unavailable = line.bed_ids.filtered(
                        lambda b: not b.is_available(
                            rec.checkin, rec.checkout, ignore_reservation=rec))
                    if unavailable:
                        raise UserError(_(
                            "Lit(s) %s de la chambre %s indisponible(s) du %s au %s.",
                            ', '.join(unavailable.mapped('name')),
                            line.room_id.name, rec.checkin, rec.checkout))
                elif not line.room_id.is_available(
                        rec.checkin, rec.checkout, ignore_reservation=rec):
                    free = line.room_id.bookable_beds(
                        rec.checkin, rec.checkout, ignore_reservation=rec)
                    if free:
                        raise UserError(_(
                            "La chambre %s ne peut pas être louée entière du %s au %s : "
                            "des lits y sont déjà loués. Lits encore libres : %s.",
                            line.room_id.name, rec.checkin, rec.checkout,
                            ', '.join(free.mapped('name'))))
                    raise UserError(_(
                        "La chambre %s n'est pas disponible du %s au %s "
                        "(maintenance ou déjà réservée).",
                        line.room_id.name, rec.checkin, rec.checkout))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hotel.reservation') or _('Nouveau')
        records = super().create(vals_list)
        for rec in records:
            source = dict(self._fields['source'].selection).get(rec.source, '')
            rec._hotel_notify_managers(_(
                "Nouvelle réservation %(name)s (%(source)s) : %(partner)s, "
                "du %(ci)s au %(co)s.",
                name=rec.name, source=source, partner=rec.partner_id.display_name,
                ci=rec.checkin, co=rec.checkout))
        return records

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_(
                    "Seule une réservation en brouillon peut être confirmée "
                    "(%(name)s est « %(state)s »).",
                    name=rec.name, state=rec._state_label()))
            if not rec.line_ids:
                raise UserError(_("Ajoutez au moins une chambre avant de confirmer."))
            rec._check_guest_places()
            rec._check_availability()
            rec.state = 'confirmed'

    def action_checkin(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(_(
                    "L'enregistrement (check-in) n'est possible que sur une "
                    "réservation confirmée (%(name)s est « %(state)s »).",
                    name=rec.name, state=rec._state_label()))
            rec._check_guest_places()
            rec._check_availability()
            rec.state = 'checkin'

    def action_checkout(self):
        for rec in self:
            if rec.state != 'checkin':
                raise UserError(_(
                    "Le départ (check-out) n'est possible que sur une réservation "
                    "enregistrée, client présent (%(name)s est « %(state)s »).",
                    name=rec.name, state=rec._state_label()))
        Housekeeping = self.env['hotel.housekeeping']
        for rec in self:
            rec.state = 'checkout'
            rooms = rec.line_ids.mapped('room_id')
            rooms.write({'housekeeping_status': 'dirty'})
            for room in rooms:
                Housekeeping.create({
                    'room_id': room.id,
                    'reservation_id': rec.id,
                    'cleaning_type': 'checkout',
                    'state': 'todo',
                })
            # Facturation automatique au départ (paramètre de la société) :
            # facture validée, acomptes déduits par lettrage.
            if rec.company_id.hotel_auto_invoice and rec.amount_total > 0 \
                    and not rec.invoice_ids.filtered(lambda m: m.state != 'cancel'):
                invoice = rec._hotel_create_invoice()
                invoice.action_post()
                rec.message_post(body=_(
                    "Facture %s générée automatiquement au départ.", invoice.name))

    def action_cancel(self):
        for rec in self:
            if rec.state == 'checkout':
                raise UserError(_(
                    "La réservation %s est terminée et ne peut plus être annulée.",
                    rec.name))
        self.write({'state': 'cancel'})
        for rec in self:
            rec._hotel_notify_managers(_(
                "Réservation annulée : %(name)s — %(partner)s (%(ci)s → %(co)s).",
                name=rec.name, partner=rec.partner_id.display_name,
                ci=rec.checkin, co=rec.checkout))

    # ------------------------------------------------------------------
    # Notifications et alertes (cahier des charges §18)
    # ------------------------------------------------------------------
    def _hotel_notify_managers(self, body):
        """Notifie (boîte de réception Odoo) les responsables de l'auberge."""
        group = self.env.ref('hotel_management.group_hotel_manager',
                             raise_if_not_found=False)
        partners = group.sudo().all_user_ids.filtered('active').partner_id \
            if group else self.env['res.partner']
        for rec in self:
            rec.sudo().message_post(
                body=body, partner_ids=partners.ids,
                message_type='comment', subtype_xmlid='mail.mt_note')

    def _hotel_schedule_alert(self, summary, note, deadline=None):
        """Activité « à faire » pour le responsable de la réservation, sans
        doublon (même résumé encore ouvert)."""
        for rec in self:
            if rec.activity_ids.filtered(lambda a: a.summary == summary):
                continue
            rec.sudo().activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=deadline or fields.Date.context_today(rec),
                summary=summary, note=note,
                user_id=(rec.user_id or rec.create_uid or self.env.user).id)

    @api.model
    def _cron_hotel_alerts(self):
        """Tâche planifiée quotidienne : arrivées et départs prévus, paiements
        en retard, stock minimum."""
        today = fields.Date.context_today(self)
        arrivals = self.search([('state', '=', 'confirmed'), ('checkin', '=', today)])
        arrivals._hotel_schedule_alert(
            _("Arrivée prévue aujourd'hui"),
            _("Préparer l'accueil du client et vérifier la chambre."))
        departures = self.search([('state', '=', 'checkin'), ('checkout', '=', today)])
        departures._hotel_schedule_alert(
            _("Départ prévu aujourd'hui"),
            _("Ajouter les consommations, encaisser le solde et faire sortir le client."))
        late = self.search([
            ('state', 'in', ('checkin', 'checkout')),
            ('checkout', '<', today),
            ('amount_due', '>', 0),
        ])
        late._hotel_schedule_alert(
            _("Paiement en retard"),
            _("Le séjour est terminé mais un reste à payer subsiste."))
        self.env['product.product']._hotel_check_stock_alerts()

    def action_draft(self):
        self.write({'state': 'draft'})

    def _state_label(self):
        self.ensure_one()
        return dict(self._fields['state'].selection).get(self.state, self.state)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft_or_cancel(self):
        """On ne supprime pas une réservation engagée : confirmée, client
        présent, terminée, ou déjà facturée. Il faut l'annuler d'abord."""
        for rec in self:
            if rec.state not in ('draft', 'cancel'):
                raise UserError(_(
                    "La réservation %(name)s est « %(state)s » et ne peut pas être "
                    "supprimée. Annulez-la d'abord (bouton « Annuler »).",
                    name=rec.name, state=rec._state_label()))
            if rec.invoice_ids.filtered(lambda m: m.state != 'cancel'):
                raise UserError(_(
                    "La réservation %(name)s possède des factures et ne peut pas "
                    "être supprimée.",
                    name=rec.name))

    @api.model
    def get_dashboard_data(self):
        """Données agrégées pour le tableau de bord hôtelier."""
        today = fields.Date.context_today(self)
        Room = self.env['hotel.room']
        Line = self.env['hotel.reservation.line']

        rooms = Room.search([])
        total_rooms = len(rooms)
        maintenance = len(rooms.filtered('maintenance'))
        out_of_service = len(rooms.filtered(lambda r: r.status == 'out_of_service'))
        cleaning = len(rooms.filtered(lambda r: r.status == 'cleaning'))
        occupied = len(rooms.filtered(lambda r: r.status == 'occupied'))
        reserved = len(rooms.filtered(lambda r: r.status == 'reserved'))
        partial = len(rooms.filtered(lambda r: r.status == 'partial'))
        # Une chambre en attente de ménage reste vendable
        available = len(rooms.filtered(lambda r: r.status in ('available', 'cleaning')))
        to_clean = len(rooms.filtered(lambda r: r.housekeeping_status == 'dirty'))
        occupancy_rate = round(
            ((occupied + partial) / total_rooms) * 100, 1) if total_rooms else 0.0

        # Occupation au lit (auberge / dortoirs)
        sellable = rooms.filtered(lambda r: not r.maintenance)
        total_beds = sum(len(r.bed_ids.filtered('active')) for r in sellable)
        free_beds = sum(r.beds_free_count for r in sellable)
        bed_occupancy_rate = round(
            ((total_beds - free_beds) / total_beds) * 100, 1) if total_beds else 0.0

        occ_lines = Line.search([
            ('state', '=', 'checkin'),
            ('checkin', '<=', today),
            ('checkout', '>=', today),
        ])

        present_guests = len(occ_lines.mapped('reservation_id.partner_id'))
        all_res = self.search([('state', '!=', 'cancel')])
        total_guests = len(all_res.mapped('partner_id'))

        arrivals_today = self.search_count([
            ('checkin', '=', today), ('state', 'in', ('confirmed', 'checkin'))])
        departures_today = self.search_count([
            ('checkout', '=', today), ('state', 'in', ('checkin', 'checkout'))])

        month_start = today.replace(day=1)
        month_res = self.search([
            ('state', '!=', 'cancel'), ('checkin', '>=', month_start)])
        month_reservations = len(month_res)
        month_revenue = sum(month_res.mapped('amount_total'))

        # Réservations à venir, encaissements et impayés (cahier des charges §15)
        upcoming = self.search([
            ('state', 'in', ('draft', 'confirmed')), ('checkin', '>', today)],
            order='checkin asc')
        upcoming_list = [{
            'id': r.id, 'name': r.name, 'partner': r.partner_id.display_name,
            'checkin': fields.Date.to_string(r.checkin),
            'rooms': ', '.join(r.line_ids.mapped('room_id.name')) or '—',
        } for r in upcoming[:8]]
        month_end = (month_start + timedelta(days=32)).replace(day=1)
        month_payments = self.env['account.payment'].sudo().search([
            ('hotel_reservation_id', '!=', False),
            ('state', 'in', ('paid', 'reconciled')),
            ('date', '>=', month_start), ('date', '<', month_end),
        ])
        month_collected = sum(month_payments.mapped('amount_company_currency_signed'))
        unpaid_res = self.search([
            ('state', 'in', ('checkin', 'checkout')), ('amount_due', '>', 0)])
        unpaid_total = sum(unpaid_res.mapped('amount_due'))
        departures = self.search([
            ('checkout', '=', today), ('state', '=', 'checkin')], limit=10)
        departures_list = [{
            'id': r.id, 'name': r.name, 'partner': r.partner_id.display_name,
            'rooms': ', '.join(r.line_ids.mapped('room_id.name')) or '—',
            'due': r.amount_due,
        } for r in departures]

        recent = self.search([], limit=8)
        recent_reservations = [{
            'id': r.id,
            'name': r.name,
            'partner': r.partner_id.display_name,
            'checkin': fields.Date.to_string(r.checkin),
            'checkout': fields.Date.to_string(r.checkout),
            'rooms': r.room_count,
            'amount': r.amount_total,
            'state': r.state,
            'state_label': dict(self._fields['state'].selection).get(r.state, r.state),
        } for r in recent]

        arrivals = self.search([
            ('checkin', '=', today), ('state', 'in', ('confirmed', 'checkin'))], limit=10)
        arrivals_list = [{
            'id': r.id, 'name': r.name, 'partner': r.partner_id.display_name,
            'rooms': ', '.join(r.line_ids.mapped('room_id.name')) or '—',
            'guests': r.guest_count,
        } for r in arrivals]

        by_type_groups = Room._read_group([], ['room_type_id'], ['__count'])
        rooms_by_type = [{
            'name': room_type.display_name if room_type else _('Sans type'),
            'count': count,
        } for room_type, count in by_type_groups]

        housekeeping_todo = self.env['hotel.housekeeping'].search_count([
            ('state', 'in', ('todo', 'inprogress'))])
        maintenance_open = self.env['hotel.maintenance.request'].search_count([
            ('state', 'in', ('new', 'inprogress'))])

        # Identifiants des enregistrements comptés par chaque tuile : un clic
        # sur la tuile ouvre exactement ces enregistrements (même filtre que
        # le chiffre affiché, y compris pour les statuts calculés non stockés).
        def room_ids(*states):
            return rooms.filtered(lambda r: r.status in states).ids

        tile_ids = {
            'occupied_rooms': room_ids('occupied'),
            'partial_rooms': room_ids('partial'),
            'available_rooms': room_ids('available', 'cleaning'),
            'reserved_rooms': room_ids('reserved'),
            'unavailable_rooms': rooms.filtered('maintenance').ids,
            'to_clean_rooms': rooms.filtered(
                lambda r: r.housekeeping_status == 'dirty').ids,
            'cleaning_free_rooms': room_ids('cleaning'),
            'all_guests': all_res.mapped('partner_id').ids,
            'present_guests': occ_lines.mapped('reservation_id.partner_id').ids,
            'arrivals_today': self.search([
                ('checkin', '=', today),
                ('state', 'in', ('confirmed', 'checkin'))]).ids,
            'departures_today': self.search([
                ('checkout', '=', today),
                ('state', 'in', ('checkin', 'checkout'))]).ids,
            'month_reservations': month_res.ids,
            'upcoming': upcoming.ids,
            'unpaid': unpaid_res.ids,
        }

        symbol = self.env.company.currency_id.symbol or ''
        return {
            'tile_ids': tile_ids,
            'housekeeping_todo': housekeeping_todo,
            'maintenance_open': maintenance_open,
            'total_rooms': total_rooms,
            'occupied': occupied,
            'reserved': reserved,
            'partial': partial,
            'available': available,
            'total_beds': total_beds,
            'free_beds': free_beds,
            'bed_occupancy_rate': bed_occupancy_rate,
            'maintenance': maintenance,
            'out_of_service': out_of_service,
            'cleaning': cleaning,
            'to_clean': to_clean,
            'occupancy_rate': occupancy_rate,
            'present_guests': present_guests,
            'total_guests': total_guests,
            'arrivals_today': arrivals_today,
            'departures_today': departures_today,
            'month_reservations': month_reservations,
            'month_revenue': month_revenue,
            'month_collected': month_collected,
            'upcoming_count': len(upcoming),
            'upcoming_list': upcoming_list,
            'departures_list': departures_list,
            'unpaid_total': unpaid_total,
            'unpaid_count': len(unpaid_res),
            'currency_symbol': symbol,
            'recent_reservations': recent_reservations,
            'arrivals_list': arrivals_list,
            'rooms_by_type': rooms_by_type,
        }


class HotelReservationLine(models.Model):
    _name = 'hotel.reservation.line'
    _description = "Ligne de réservation (chambre)"

    reservation_id = fields.Many2one(
        'hotel.reservation', string="Réservation", required=True, ondelete='cascade')
    room_id = fields.Many2one('hotel.room', string="Chambre", required=True)
    booking_type = fields.Selection(
        related='reservation_id.booking_type', string="Type de location",
        store=True, readonly=True)
    bed_ids = fields.Many2many('hotel.bed', string="Lits")
    available_bed_ids = fields.Many2many(
        'hotel.bed', 'hotel_resline_avail_bed_rel', 'line_id', 'bed_id',
        string="Lits disponibles", compute='_compute_available_bed_ids',
        help="Lits libres de la chambre sur la période : seuls ceux-ci sont "
             "proposés à la sélection.")
    rental_mode = fields.Selection(related='room_id.rental_mode')
    room_type_id = fields.Many2one(
        related='room_id.room_type_id', string="Type", store=True)
    checkin = fields.Date(related='reservation_id.checkin', store=True)
    checkout = fields.Date(related='reservation_id.checkout', store=True)
    nights = fields.Integer(related='reservation_id.nights', store=True)
    price_unit = fields.Monetary(string="Prix / nuit", currency_field='currency_id')
    price_subtotal = fields.Monetary(
        string="Sous-total", compute='_compute_subtotal', store=True)
    currency_id = fields.Many2one(related='reservation_id.currency_id', store=True)
    partner_id = fields.Many2one(related='reservation_id.partner_id', store=True)
    state = fields.Selection(related='reservation_id.state', store=True)

    def _get_places(self):
        """Nombre de personnes que la ligne permet d'accueillir."""
        self.ensure_one()
        if self.booking_type == 'bed':
            return len(self.bed_ids)
        return self.room_id.capacity or len(self.room_id.bed_ids.filtered('active'))

    @api.depends('price_unit', 'nights')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.price_unit * (line.nights or 0)

    @api.depends('room_id', 'checkin', 'checkout', 'reservation_id.state', 'bed_ids')
    def _compute_available_bed_ids(self):
        for line in self:
            room = line.room_id
            if room and line.checkin and line.checkout:
                avail = room.available_beds(
                    line.checkin, line.checkout,
                    ignore_reservation=line.reservation_id._origin)
            elif room:
                avail = room.bed_ids.filtered('active')
            else:
                avail = self.env['hotel.bed']
            # Les lits déjà sélectionnés restent visibles même s'ils ne sont
            # plus « libres » (c'est cette ligne qui les occupe).
            line.available_bed_ids = avail | line.bed_ids

    def _apply_price(self):
        """Prix / nuit de la ligne : tarif spécial du client, sinon tarif
        saisonnier nuit par nuit, sinon prix de la chambre (ou du lit × nb lits)."""
        if not self.room_id:
            return
        resa = self.reservation_id
        unit = self.room_id._get_stay_unit_price(
            resa.checkin, resa.checkout, self.booking_type, resa.partner_id)
        if self.booking_type == 'bed':
            self.price_unit = len(self.bed_ids) * unit
        else:
            self.price_unit = unit

    def _invoice_label(self):
        self.ensure_one()
        if self.booking_type == 'bed' and self.bed_ids:
            return _("Chambre %(room)s — lit(s) %(beds)s — %(nights)s nuit(s)",
                     room=self.room_id.name, beds=', '.join(self.bed_ids.mapped('name')),
                     nights=self.nights)
        return _("Chambre %(room)s — chambre entière — %(nights)s nuit(s)",
                 room=self.room_id.name, nights=self.nights)

    def _apply_booking_type(self):
        """Aligne les lits de la ligne sur le « Type de location » de la
        réservation : chambre entière -> tous les lits ; par lit -> sélection
        vidée pour que l'utilisateur choisisse les lits disponibles."""
        if self.booking_type == 'room':
            self.bed_ids = [(6, 0, self.room_id.bed_ids.filtered('active').ids)]
        else:
            self.bed_ids = [(5, 0, 0)]
        self._apply_price()

    @api.onchange('room_id')
    def _onchange_room_id(self):
        if self.room_id:
            self._apply_booking_type()

    @api.onchange('bed_ids')
    def _onchange_bed_ids(self):
        if self.bed_ids:
            rooms = self.bed_ids.mapped('room_id')
            if len(rooms) > 1:
                self.bed_ids = self.bed_ids.filtered(lambda b: b.room_id == rooms[0])
            if not self.room_id:
                self.room_id = rooms[0]
        self._apply_price()

    @api.onchange('booking_type')
    def _onchange_booking_type(self):
        if self.booking_type == 'room':
            # Chambre entière : récupère automatiquement tous les lits.
            self.bed_ids = [(6, 0, self.room_id.bed_ids.filtered('active').ids)]
        else:
            # Par lit : l'utilisateur sélectionne les lits disponibles.
            self.bed_ids = [(5, 0, 0)]
        self._apply_price()

    @api.constrains('price_unit')
    def _check_price_unit(self):
        for line in self:
            if line.price_unit < 0:
                raise ValidationError(_(
                    "Le prix par nuit d'une chambre ne peut pas être négatif."))

    @api.constrains('room_id', 'reservation_id')
    def _check_unique_room_per_reservation(self):
        """Une même chambre ne doit figurer qu'une fois par réservation :
        les lits se regroupent sur une seule ligne."""
        for line in self:
            if not (line.room_id and line.reservation_id):
                continue
            twin = line.reservation_id.line_ids.filtered(
                lambda l: l.room_id == line.room_id and l.id != line.id)
            if twin:
                raise ValidationError(_(
                    "La chambre %(room)s figure plusieurs fois dans la "
                    "réservation %(res)s. Regroupez-la sur une seule ligne "
                    "(et, en mode « par lit », sélectionnez-y tous les lits voulus).",
                    room=line.room_id.name, res=line.reservation_id.name))

    @api.constrains('booking_type', 'bed_ids', 'room_id')
    def _check_beds(self):
        for line in self:
            if line.booking_type == 'bed':
                if not line.room_id.bed_ids.filtered('active'):
                    raise ValidationError(_(
                        "La chambre %s n'a aucun lit : réservez-la en chambre "
                        "entière, ou ajoutez-lui des lits (Configuration).",
                        line.room_id.name))
                if not line.bed_ids:
                    raise ValidationError(_(
                        "Sélectionnez au moins un lit pour une réservation par lit."))
                if any(b.room_id != line.room_id for b in line.bed_ids):
                    raise ValidationError(_(
                        "Tous les lits doivent appartenir à la chambre sélectionnée."))
