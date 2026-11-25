from datetime import timedelta

from markupsafe import Markup

from odoo import Command, api, fields, models, _
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

    # Pas required au niveau du modèle : la section « Client principal » se
    # remplit aussi sans choisir de contact, la fiche client est alors créée
    # à l'enregistrement (voir create / _check_partner_set).
    partner_id = fields.Many2one(
        'res.partner', string="Client", tracking=True, index=True)
    # Coordonnées et pièce d'identité du client, modifiables depuis la réservation
    partner_last_name = fields.Char(
        related='partner_id.hotel_last_name', readonly=False, string="Nom")
    partner_first_name = fields.Char(
        related='partner_id.hotel_first_name', readonly=False, string="Prénom")
    partner_phone = fields.Char(
        related='partner_id.phone', readonly=False, string="Téléphone")
    # Profil client : rempli depuis la fiche client, et une modification
    # faite ici est enregistrée sur la fiche client.
    partner_customer_type_id = fields.Many2one(
        related='partner_id.hotel_customer_type_id', readonly=False,
        string="Type de client")
    partner_is_blacklisted = fields.Boolean(
        related='partner_id.hotel_customer_type_id.is_blacklist',
        string="Client en alerte")
    partner_customer_type_name = fields.Char(
        related='partner_id.hotel_customer_type_id.name',
        string="Libellé type de client")
    partner_preferences = fields.Text(
        related='partner_id.hotel_preferences', readonly=False,
        string="Préférences")
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
    # Saisie : nombre d'adultes et nombre d'enfants ; le total de personnes
    # en découle (adultes + enfants). Écrire « guest_count » reste possible
    # (site web, imports, code) : les adultes sont alors personnes - enfants.
    adults = fields.Integer(string="Adultes", default=1, required=True)
    children = fields.Integer(string="Enfants", default=0)
    guest_ids = fields.One2many(
        'hotel.reservation.guest', 'reservation_id', string="Autres personnes",
        copy=False,
        help="Une fiche par adulte (en plus du client) et par enfant : elles "
             "suivent automatiquement le nombre d'adultes et d'enfants.")
    # Mêmes fiches, séparées pour l'affichage : section Adultes puis Enfants
    guest_adult_ids = fields.One2many(
        'hotel.reservation.guest', 'reservation_id', string="Autres adultes",
        domain=[('guest_type', '=', 'adult')], copy=False)
    guest_child_ids = fields.One2many(
        'hotel.reservation.guest', 'reservation_id', string="Enfants du séjour",
        domain=[('guest_type', '=', 'child')], copy=False)
    room_type_id = fields.Many2one(
        'hotel.room.type', string="Type de chambre", tracking=True,
        help="Fixe le prix de la réservation : « Prix chambre » du type pour une "
             "location par chambre, « Prix lit » pour une location par lit.")
    floor_id = fields.Many2one(
        'hotel.floor', string="Étage", tracking=True, index=True,
        help="Seules les chambres / lits de cet étage sont proposés ; toutes les "
             "chambres de la réservation doivent être à cet étage.")
    guest_count = fields.Integer(
        string="Personnes", compute='_compute_guest_count',
        inverse='_inverse_guest_count', store=True, readonly=False,
        help="Nombre total de personnes du séjour = adultes + enfants.")
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
        help="Par chambre : chaque chambre réservée est prise en entier, avec "
             "tous ses lits.\n"
             "Par lit : on choisit les lits un par un ; la chambre de chaque lit "
             "est déduite automatiquement.")
    proposed_room_ids = fields.Many2many(
        'hotel.room', 'hotel_resa_proposed_room_rel', 'reservation_id', 'room_id',
        string="Chambres proposées", compute='_compute_proposed')
    proposed_bed_ids = fields.Many2many(
        'hotel.bed', 'hotel_resa_proposed_bed_rel', 'reservation_id', 'bed_id',
        string="Lits proposés", compute='_compute_proposed')
    # Ordre d'affichage des propositions dans la liste de choix (ids séparés
    # par des virgules) : même logique que la recherche du site web.
    proposed_room_order = fields.Char(compute='_compute_proposed')
    proposed_bed_order = fields.Char(compute='_compute_proposed')
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

    def _inverse_guest_count(self):
        for rec in self:
            rec.adults = (rec.guest_count or 0) - (rec.children or 0)

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
        """Tarifs spéciaux du client appliqués à la réservation (la remise,
        elle, se saisit sur la réservation)."""
        for line in self.line_ids:
            line._apply_price()
        if self.partner_id.hotel_customer_type_id.is_blacklist:
            return {'warning': {
                'title': _("Client en %s", self.partner_id.hotel_customer_type_id.name),
                'message': _(
                    "Attention : %(client)s est classé « %(type)s ».\n"
                    "Vérifiez avec un responsable avant de confirmer la réservation.",
                    client=self.partner_id.display_name,
                    type=self.partner_id.hotel_customer_type_id.name),
            }}

    @api.onchange('checkin', 'checkout')
    def _onchange_dates_free_only(self):
        """Nouvelles dates : seuls les lits / chambres libres sur la nouvelle
        période restent dans la réservation. Ceux déjà pris par une autre
        réservation (brouillon compris, comme pour les propositions) sur ces
        dates sont retirés, avec un avertissement."""
        if not (self.checkin and self.checkout and self.checkout > self.checkin):
            return
        origin = self._origin if self._origin else False
        removed = []
        to_remove = self.env['hotel.reservation.line']
        for line in self.line_ids.with_context(hotel_include_draft=True):
            if not line.room_id:
                continue
            if self.booking_type == 'bed':
                beds = line.bed_id or line.bed_ids
                taken = beds.filtered(lambda b: not b.is_available(
                    self.checkin, self.checkout, ignore_reservation=origin))
                if taken:
                    to_remove |= line
                    removed.append(_("lit %(beds)s (chambre %(room)s)",
                                     beds=", ".join(taken.mapped('name')),
                                     room=line.room_id.name))
            elif not line.room_id.is_available(
                    self.checkin, self.checkout, ignore_reservation=origin):
                to_remove |= line
                removed.append(_("chambre %s", line.room_id.name))
        if not to_remove:
            return
        self.line_ids -= to_remove
        return {'warning': {
            'title': _("Lits / chambres plus disponibles"),
            'message': _(
                "Sur la période du %(start)s au %(end)s, ces éléments sont déjà "
                "réservés et ont été retirés : %(items)s.\n"
                "Choisissez parmi les lits / chambres proposés.",
                start=self.checkin.strftime('%d/%m/%Y'),
                end=self.checkout.strftime('%d/%m/%Y'),
                items="; ".join(removed)),
        }}

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

    @api.constrains('guest_count', 'adults', 'children')
    def _check_guest_counts(self):
        for rec in self:
            if (rec.adults or 0) < 1:
                raise ValidationError(_(
                    "Une réservation doit compter au moins un adulte."))
            if (rec.children or 0) < 0:
                raise ValidationError(_(
                    "Le nombre d'enfants ne peut pas être négatif."))

    @api.onchange('floor_id')
    def _onchange_floor_id(self):
        """Changement d'étage : les chambres / lits d'un autre étage sont retirés."""
        if not self.floor_id:
            return
        other = self.line_ids.filtered(
            lambda l: l.room_id and l.room_id.floor_id != self.floor_id)
        if other:
            rooms = ', '.join(sorted(set(other.room_id.mapped('name'))))
            self.line_ids -= other
            return {'warning': {
                'type': 'notification',
                'title': _("Étage modifié"),
                'message': _("Chambre(s) retirée(s), autre étage : %s", rooms),
            }}

    @api.constrains('floor_id', 'line_ids')
    def _check_floor(self):
        for rec in self.filtered('floor_id'):
            other = rec.line_ids.room_id.filtered(lambda r: r.floor_id != rec.floor_id)
            if other:
                raise ValidationError(_(
                    "Réservation %(resa)s : la chambre %(rooms)s n'est pas à l'étage "
                    "« %(floor)s ». Choisissez des chambres de cet étage ou changez d'étage.",
                    resa=rec.name or '', rooms=', '.join(other.mapped('name')),
                    floor=rec.floor_id.name))

    @api.onchange('room_type_id')
    def _onchange_room_type_reprice(self):
        """Nouveau type de chambre : prix des lignes recalculés."""
        for line in self.line_ids:
            line._apply_price()

    def _bed_count_message(self):
        """Location par lit : il faut exactement un lit par personne.
        Message d'erreur si ce n'est pas le cas, sinon False."""
        self.ensure_one()
        if self.booking_type != 'bed' or self.state in ('cancel', 'checkout'):
            return False
        beds = len(self.line_ids.bed_ids)
        if beds != (self.guest_count or 0):
            return _(
                "Réservation par lit : le nombre de lits sélectionnés (%(beds)s) "
                "doit être égal au nombre de personnes (%(guests)s).\n\n"
                "Ajoutez ou retirez des lits, ou corrigez le nombre d'adultes / "
                "d'enfants.",
                beds=beds, guests=self.guest_count or 0)
        return False

    _BED_COUNT_FIELDS = {'state', 'booking_type', 'line_ids', 'guest_count', 'adults', 'children'}

    def _check_bed_count(self):
        # Vérifié en fin de create/write (et pas via @api.constrains) : le
        # recalcul de guest_count déclenche les contraintes en cours
        # d'écriture, avant la suppression des lits retirés dans le même
        # enregistrement.
        for rec in self:
            message = rec._bed_count_message()
            if message:
                raise ValidationError(message)

    @api.constrains('state', 'checkin', 'checkout', 'line_ids', 'guest_count', 'adults', 'children')
    def _check_booking_integrity(self):
        """Toute modification d'une réservation déjà confirmée ou enregistrée
        est revalidée : places suffisantes et aucune surréservation. Sans cela,
        changer les dates ou les chambres d'une réservation confirmée pouvait
        créer un conflit sans alerte."""
        for rec in self:
            if rec.state in ('confirmed', 'checkin'):
                rec._check_guest_places()
                rec._check_availability()

    @api.depends('checkin', 'checkout', 'booking_type', 'floor_id',
                 'guest_count', 'children', 'line_ids.room_id', 'line_ids.bed_ids')
    def _compute_proposed(self):
        """Chambres / lits proposés dans les lignes : seulement les chambres
        dont le nombre de lits (libres) = nombre de personnes restant à loger,
        à défaut + 1, puis + 2… (voir hotel.room._hotel_ordered_free_rooms /
        _hotel_ordered_free_beds). Seulement les chambres de l'étage choisi."""
        Room = self.env['hotel.room']
        for rec in self:
            origin = rec._origin if rec._origin else False
            checkin, checkout = rec._proposal_period()
            domain = [('floor_id', '=', rec.floor_id.id)] if rec.floor_id else None
            guests = max(rec.guest_count or 1, 1)
            if rec.booking_type == 'room':
                rooms = Room._hotel_ordered_free_rooms(
                    checkin, checkout, origin, guests, rec.line_ids.room_id._origin, domain)
                rec.proposed_room_ids = rooms
                rec.proposed_room_order = ','.join(str(i) for i in rooms.ids)
                rec.proposed_bed_ids = False
                rec.proposed_bed_order = False
            else:
                beds = Room._hotel_ordered_free_beds(
                    checkin, checkout, origin, guests, rec.line_ids.bed_ids._origin, domain)
                rec.proposed_room_ids = False
                rec.proposed_room_order = False
                rec.proposed_bed_ids = beds
                rec.proposed_bed_order = ','.join(str(i) for i in beds.ids)

    # ------------------------------------------------------------------
    # Personnes du séjour : une fiche par adulte (hors client) et par enfant
    # ------------------------------------------------------------------
    def _guest_sync_plan(self):
        """(fiches en trop, valeurs des fiches à créer) pour que les fiches
        correspondent aux nombres d'adultes / d'enfants."""
        self.ensure_one()
        to_remove = self.env['hotel.reservation.guest']
        to_create = []
        adults = self.adults or 1
        wanted = {'adult': max(adults - 1, 0),
                  'child': max(self.children or 0, 0)}
        first_position = {'adult': 2, 'child': 1}
        for kind, count in wanted.items():
            guests = self[self._GUEST_FIELDS[kind]].sorted(lambda g: (g.position or 0))
            to_remove |= guests[count:]
            kept = guests[:count]
            position = max(kept.mapped('position') or [first_position[kind] - 1])
            for _i in range(count - len(kept)):
                position += 1
                to_create.append({'guest_type': kind, 'position': position})
        return to_remove, to_create

    @api.onchange('adults', 'children', 'guest_count')
    def _onchange_guest_counts(self):
        to_remove, to_create = self._guest_sync_plan()
        if not to_remove and not to_create:
            return
        Guest = self.env['hotel.reservation.guest']
        for kind, fname in self._GUEST_FIELDS.items():
            new_guests = Guest
            for vals in to_create:
                if vals['guest_type'] == kind:
                    new_guests += Guest.new(vals)
            if new_guests or (self[fname] & to_remove):
                self[fname] = (self[fname] - to_remove) + new_guests

    def _sync_guests(self):
        """Même règle hors écran (site web, import, code)."""
        self.invalidate_recordset(list(self._GUEST_FIELDS.values()))
        for rec in self:
            to_remove, to_create = rec._guest_sync_plan()
            commands = [Command.unlink(g.id) for g in to_remove]
            commands += [Command.create(vals) for vals in to_create]
            if commands:
                rec.with_context(hotel_guest_sync=True).write({'guest_ids': commands})

    def _proposal_period(self):
        """Période servant à filtrer les propositions. Dates incomplètes
        (ex. nouvelle réservation : départ pas encore saisi) : au moins une
        nuit à partir de l'arrivée (ou d'aujourd'hui), pour ne jamais
        proposer une chambre ou un lit déjà réservé."""
        self.ensure_one()
        checkin = self.checkin or fields.Date.context_today(self)
        checkout = self.checkout
        if not checkout or checkout <= checkin:
            checkout = checkin + timedelta(days=1)
        return checkin, checkout

    @api.onchange('booking_type')
    def _onchange_booking_type(self):
        """Changement de type de location : les lignes sont converties.
        Par chambre -> par lit : une ligne par lit de chaque chambre ;
        par lit -> par chambre : une ligne par chambre (tous ses lits).
        Le type de chambre choisi est conservé (aucun lien entre type de
        location et type de chambre)."""
        if not self.line_ids:
            return
        rooms = self.line_ids.room_id
        commands = [(5, 0, 0)]
        if self.booking_type == 'bed':
            for line in self.line_ids:
                for bed in (line.bed_ids or line.room_id.bed_ids.filtered('active')):
                    commands.append((0, 0, {'room_id': bed.room_id.id, 'bed_id': bed.id,
                                            'bed_ids': [(6, 0, bed.ids)]}))
        else:
            for room in rooms:
                commands.append((0, 0, {
                    'room_id': room.id,
                    'bed_ids': [(6, 0, room.bed_ids.filtered('active').ids)]}))
        self.line_ids = commands
        for line in self.line_ids:
            line._apply_price()

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

    def _send_confirmation_mails(self):
        """Envoie l'e-mail de confirmation ; renvoie (envoyées, sans e-mail)."""
        template = self.env.ref(
            'hotel_management.mail_template_reservation_confirmation',
            raise_if_not_found=False)
        if not template:
            raise UserError(_("Le modèle d'e-mail de confirmation est introuvable."))
        sent = self.filtered(lambda r: r.partner_id.email)
        for rec in sent:
            template.sudo().send_mail(rec.id, force_send=True)
        return sent, self - sent

    def _send_request_received_mails(self):
        """E-mail « demande reçue » envoyé au client après une réservation
        sur le site (la réservation reste en brouillon)."""
        template = self.env.ref(
            'hotel_management.mail_template_reservation_received',
            raise_if_not_found=False)
        if not template:
            return
        for rec in self.filtered(lambda r: r.partner_id.email):
            rec._portal_ensure_token()  # lien « Télécharger mon reçu »
            template.sudo().send_mail(rec.id, force_send=True)

    def _confirmation_notification(self, sent, no_email):
        lines = []
        if sent:
            lines.append(_("Confirmation envoyée : %s", ', '.join(sent.mapped('name'))))
        if no_email:
            lines.append(_("Client sans e-mail (non envoyé) : %s",
                           ', '.join(no_email.mapped('name'))))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Envoi des confirmations"),
                'message': '\n'.join(lines),
                'type': 'success' if sent and not no_email else 'warning',
                'sticky': bool(no_email),
            },
        }

    def action_send_confirmation(self):
        """Bouton « Envoyer confirmation » de la fiche réservation."""
        sent, no_email = self._send_confirmation_mails()
        return self._confirmation_notification(sent, no_email)

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

    _GUEST_FIELDS = {'adult': 'guest_adult_ids', 'child': 'guest_child_ids'}

    def _partner_related_fields(self):
        """{champ de la réservation: champ du contact} pour les coordonnées du
        client modifiables depuis la réservation (related partner_id.xxx)."""
        return {
            name: field.related.split('.', 1)[1]
            for name, field in self._fields.items()
            if field.related and field.related.startswith('partner_id.')
            and field.related.count('.') == 1 and not field.readonly
        }

    def _create_partner_from_vals(self, vals):
        """Client saisi directement dans la section « Client principal » sans
        choisir de contact : la fiche client est créée avec ces informations."""
        mapping = self._partner_related_fields()
        partner_vals = {mapping[k]: vals.pop(k) for k in list(vals) if k in mapping}
        partner_vals = {k: v for k, v in partner_vals.items() if v}
        if not (partner_vals.get('hotel_last_name') or partner_vals.get('hotel_first_name')):
            raise UserError(_(
                "Indiquez le client principal : choisissez un client existant, "
                "ou saisissez au moins son nom."))
        return self.env['res.partner'].create(partner_vals)

    @api.onchange('partner_last_name', 'partner_first_name')
    def _onchange_partner_names_create(self):
        """Nouveau client : dès que nom ET prénom sont saisis (sans contact
        choisi), le contact est créé et sélectionné dans « Client ». Ce qui a
        déjà été saisi (téléphone, naissance…) est repris sur sa fiche ; la
        suite est enregistrée sur la fiche à l'enregistrement de la réservation."""
        if self.partner_id or not (self.partner_last_name and self.partner_first_name):
            return
        warning = self._homonym_warning(self.partner_last_name, self.partner_first_name)
        if warning:
            # Client peut-être déjà connu : simple notification (non bloquante).
            # Pas de création immédiate : si c'est bien une autre personne,
            # le contact est créé à l'enregistrement de la réservation.
            return warning
        partner_vals = {}
        for fname, partner_field in self._partner_related_fields().items():
            value = self[fname]
            if self._fields[fname].type == 'many2one':
                value = value.id
            if value:
                partner_vals[partner_field] = value
        self.partner_id = self.env['res.partner'].create(partner_vals)

    @api.onchange('partner_id_number')
    def _onchange_partner_id_number(self):
        """Alerte immédiate si le n° de pièce saisi appartient déjà à un autre
        contact (l'enregistrement sera refusé)."""
        Partner = self.env['res.partner']
        existing = Partner._hotel_find_id_number(
            self.partner_id_number, exclude=self.partner_id._origin)
        if existing:
            return {'warning': {
                'title': _("Pièce d'identité déjà enregistrée"),
                'message': Partner._hotel_id_number_message(self.partner_id_number, existing)}}

    @api.model
    def _homonym_warning(self, last_name, first_name):
        """Avertissement (dict onchange) si un contact porte déjà ce nom et
        ce prénom, sinon False. Sert au client principal et aux autres
        personnes du séjour."""
        homonyms = self._find_homonym_partners(last_name, first_name)
        if not homonyms:
            return False
        lines = []
        for partner in homonyms[:5]:
            details = [d for d in (
                partner.phone,
                partner.hotel_birthdate and _("né(e) le %s", partner.hotel_birthdate.strftime('%d/%m/%Y')),
                partner.hotel_id_number and _("pièce n° %s", partner.hotel_id_number),
            ) if d]
            lines.append("• %s%s" % (partner.display_name, details and " (%s)" % ", ".join(details) or ""))
        return {'warning': {
            'type': 'notification',
            'title': _("Ce client existe peut-être déjà"),
            'message': _(
                "Un contact porte déjà ce nom :\n%(list)s\n\n"
                "S'il s'agit de la même personne, choisissez-le dans le champ "
                "« %(field)s ».\n"
                "Sinon, continuez la saisie : un nouveau contact sera créé à "
                "l'enregistrement.",
                list="\n".join(lines),
                field=self.env.context.get('hotel_homonym_field') or _("Client")),
        }}

    @api.model
    def _find_homonym_partners(self, last_name, first_name):
        """Contacts portant déjà ce nom et ce prénom (casse et espaces ignorés)."""
        last, first = (last_name or '').strip(), (first_name or '').strip()
        if not (last and first):
            return self.env['res.partner']
        return self.env['res.partner'].search([
            '|', '|',
            '&', ('hotel_last_name', '=ilike', last), ('hotel_first_name', '=ilike', first),
            ('name', '=ilike', "%s %s" % (last, first)),
            ('name', '=ilike', "%s %s" % (first, last)),
        ], limit=10)

    @api.constrains('partner_id')
    def _check_partner_set(self):
        for rec in self:
            if not rec.partner_id:
                raise ValidationError(_("Le client principal est obligatoire."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('partner_id'):
                vals['partner_id'] = self._create_partner_from_vals(vals).id
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hotel.reservation') or _('Nouveau')
        records = super().create(vals_list)
        records._check_bed_count()
        records._sync_guests()
        for rec in records:
            if rec.source == 'website' and rec._hotel_post_online_channel():
                continue
            source = dict(self._fields['source'].selection).get(rec.source, '')
            rec._hotel_notify_managers(_(
                "Nouvelle réservation %(name)s (%(source)s) : %(partner)s, "
                "du %(ci)s au %(co)s.",
                name=rec.name, source=source, partner=rec.partner_id.display_name,
                ci=rec.checkin, co=rec.checkout))
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'booking_type' in vals:
            self.line_ids._force_room_beds()
        if self._BED_COUNT_FIELDS & set(vals):
            self._check_bed_count()
        if ('adults' in vals or 'children' in vals or 'guest_count' in vals) \
                and not self.env.context.get('hotel_guest_sync'):
            self._sync_guests()
        return res

    def _identity_missing(self):
        """Liste des informations obligatoires manquantes (client principal et
        autres adultes du séjour), pour bloquer confirmation et check-in."""
        self.ensure_one()
        partner_fields = [
            ('hotel_last_name', _("Nom")), ('hotel_first_name', _("Prénom")),
            ('hotel_birthdate', _("Date de naissance")), ('phone', _("Téléphone")),
            ('street', _("Adresse")), ('hotel_id_type', _("Type de pièce d'identité")),
            ('hotel_id_number', _("N° de pièce d'identité")),
        ]
        guest_fields = [
            ('last_name', _("Nom")), ('first_name', _("Prénom")),
            ('birthdate', _("Date de naissance")), ('phone', _("Téléphone")),
            ('id_type', _("Type de pièce d'identité")), ('id_number', _("N° de pièce d'identité")),
        ]
        problems = []
        if not self.partner_id:
            problems.append(_("Client principal : à renseigner"))
        else:
            missing = [label for f, label in partner_fields if not self.partner_id[f]]
            if missing:
                problems.append(_("Client principal (%(name)s) : %(missing)s",
                                  name=self.partner_id.display_name, missing=", ".join(missing)))
        for index, guest in enumerate(self.guest_adult_ids.sorted(lambda g: g.position or 0), start=2):
            missing = [label for f, label in guest_fields if not guest[f]]
            if missing:
                problems.append(_("Adulte %(n)s (%(name)s) : %(missing)s",
                                  n=index, name=guest.name or _("sans nom"),
                                  missing=", ".join(missing)))
        return problems

    def _check_identity_complete(self, action_label):
        if self.env.context.get('hotel_skip_identity_check'):
            return
        for rec in self:
            problems = rec._identity_missing()
            if problems:
                raise UserError(_(
                    "%(action)s impossible pour %(name)s : informations obligatoires "
                    "manquantes.\n\n%(list)s\n\nComplétez la fiche puis réessayez.",
                    action=action_label, name=rec.name,
                    list="\n".join("• " + p for p in problems)))

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_(
                    "Seule une réservation en brouillon peut être confirmée "
                    "(%(name)s est « %(state)s »).",
                    name=rec.name, state=rec._state_label()))
            if not rec.line_ids:
                raise UserError(_("Ajoutez au moins une chambre avant de confirmer."))
            rec._check_identity_complete(_("Confirmation"))
            message = rec._bed_count_message()
            if message:
                raise UserError(message)
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
            rec._check_identity_complete(_("Check-in"))
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
            # Location au lit (dortoir) : seuls les lits libérés sont à
            # nettoyer ; la chambre, partagée avec d'autres clients, ne change
            # pas d'état. Chambre entière : ménage de toute la chambre.
            bed_lines = rec.line_ids.filtered(
                lambda l: l.booking_type == 'bed' and (l.bed_id or l.bed_ids))
            room_lines = rec.line_ids - bed_lines
            rooms = room_lines.mapped('room_id')
            rooms.write({'housekeeping_status': 'dirty'})
            rooms.bed_ids.sudo().write({'housekeeping_status': 'dirty'})
            for room in rooms:
                Housekeeping.create({
                    'room_id': room.id,
                    'reservation_id': rec.id,
                    'cleaning_type': 'checkout',
                    'state': 'todo',
                })
            beds = bed_lines.mapped('bed_id') | bed_lines.mapped('bed_ids')
            for room in beds.room_id - rooms:
                Housekeeping.create({
                    'room_id': room.id,
                    'target': 'bed',
                    'bed_ids': [(6, 0, beds.filtered(lambda b: b.room_id == room).ids)],
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

    def _hotel_post_online_channel(self):
        """Annonce une réservation faite sur le site dans le canal Discuss
        « Réservations en ligne » (au lieu d'une notification en boîte de
        réception). Renvoie False si le canal n'existe plus."""
        self.ensure_one()
        channel = self.env.ref('hotel_management.channel_online_reservations',
                               raise_if_not_found=False)
        if not channel:
            return False
        rec = self.sudo()
        partner = rec.partner_id
        rooms = ', '.join(rec.line_ids.mapped('room_id.name')) or '—'
        beds = ', '.join(rec.line_ids.mapped('bed_ids.name'))
        url = '/odoo/action-hotel_management.action_hotel_reservation_online/%s' % rec.id
        amount = rec.currency_id.format(rec.amount_total) if rec.currency_id else rec.amount_total
        body = Markup(
            "<p><b>Nouvelle réservation en ligne</b> : "
            "<a href=\"%(url)s\">%(name)s</a></p>"
            "<ul>"
            "<li>Client : %(partner)s — %(phone)s — %(email)s</li>"
            "<li>Séjour : du %(ci)s au %(co)s (%(nights)s nuit(s)), %(guests)s personne(s)</li>"
            "<li>Chambre(s) : %(rooms)s%(beds)s</li>"
            "<li>Total : %(amount)s</li>"
            "</ul>"
            "<p>À vérifier et confirmer (réservation en brouillon).</p>"
        ) % {
            'url': url, 'name': rec.name,
            'partner': partner.display_name, 'phone': partner.phone or '—',
            'email': partner.email or '—',
            'ci': rec.checkin.strftime('%d/%m/%Y') if rec.checkin else '',
            'co': rec.checkout.strftime('%d/%m/%Y') if rec.checkout else '',
            'nights': rec.nights, 'guests': rec.guest_count,
            'rooms': rooms, 'beds': (' — lit(s) : %s' % beds) if beds else '',
            'amount': amount,
        }
        channel.sudo().message_post(
            body=body, author_id=self.env.ref('base.partner_root').id,
            message_type='comment', subtype_xmlid='mail.mt_comment')
        # Trace dans l'historique de la réservation (sans notifier personne)
        rec.message_post(body=_("Réservation reçue depuis le site web."),
                         message_type='comment', subtype_xmlid='mail.mt_note')
        return True

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
    def get_dashboard_data(self, date_from=None, date_to=None):
        """Données agrégées pour le tableau de bord hôtelier.
        date_from / date_to (« AAAA-MM-JJ », inclus) : période du bloc « Sur la
        période » (réservations, CA, encaissements, nuitées, occupation moyenne).
        Par défaut : aujourd'hui. Les autres indicateurs
        (chambres, clients présents, arrivées / départs…) restent en temps réel."""
        today = fields.Date.context_today(self)
        date_from = fields.Date.to_date(date_from) or today
        date_to = fields.Date.to_date(date_to) or today
        if date_from > date_to:
            date_from, date_to = date_to, date_from
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
        all_active_beds = sum(len(r.bed_ids.filtered('active')) for r in rooms)

        # Statistiques des lits (bloc « Lits ») : statut du jour de chaque lit actif
        beds = self.env['hotel.bed'].search([])
        bed_groups = {key: beds.filtered(lambda b, k=key: b.status == k)
                      for key in ('reserved', 'occupied')}
        # Un lit en attente de ménage reste vendable : compté libre
        bed_groups['free'] = beds.filtered(lambda b: b.status in ('free', 'cleaning'))
        beds_unavailable = beds.filtered(
            lambda b: b.status in ('maintenance', 'out_of_service'))
        beds_to_clean = beds.filtered(
            lambda b: b.housekeeping_status in ('dirty', 'inprogress'))

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

        # --- Période choisie : réservations dont l'arrivée tombe dans la période
        month_res = self.search([
            ('state', '!=', 'cancel'),
            ('checkin', '>=', date_from), ('checkin', '<=', date_to)])
        month_reservations = len(month_res)
        month_revenue = sum(month_res.mapped('amount_total'))

        # Nuitées vendues sur la période (place x nuit, une nuit = du jour d au
        # lendemain) et occupation moyenne des lits.
        period_end = fields.Date.add(date_to, days=1)
        period_days = (period_end - date_from).days
        night_lines = Line.search([
            ('state', '!=', 'cancel'),
            ('checkin', '<', period_end), ('checkout', '>', date_from)])
        period_nights = 0
        for line in night_lines:
            nights = (min(line.checkout, period_end) - max(line.checkin, date_from)).days
            if nights > 0:
                period_nights += nights * line._get_places()

        # Réservations à venir, encaissements et impayés (cahier des charges §15)
        upcoming = self.search([
            ('state', 'in', ('draft', 'confirmed')), ('checkin', '>', today)],
            order='checkin asc')
        upcoming_list = [{
            'id': r.id, 'name': r.name, 'partner': r.partner_id.display_name,
            'checkin': fields.Date.to_string(r.checkin),
            'rooms': ', '.join(r.line_ids.mapped('room_id.name')) or '—',
        } for r in upcoming[:8]]
        month_payments = self.env['account.payment'].sudo().search([
            ('hotel_reservation_id', '!=', False),
            ('state', 'in', ('paid', 'reconciled')),
            ('date', '>=', date_from), ('date', '<=', date_to),
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

        # Réservations en cours (confirmées / enregistrées) par type de chambre
        by_type_groups = self._read_group(
            [('state', 'in', ('confirmed', 'checkin'))], ['room_type_id'], ['__count'])
        rooms_by_type = [{
            'name': room_type.display_name if room_type else _('Sans type'),
            'count': count,
        } for room_type, count in by_type_groups]

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
            'all_beds': beds.ids,
            'occupied_beds': bed_groups['occupied'].ids,
            'reserved_beds': bed_groups['reserved'].ids,
            'free_beds': bed_groups['free'].ids,
            'unavailable_beds': beds_unavailable.ids,
            'to_clean_beds': beds_to_clean.ids,
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
            'beds': {
                'total': len(beds),
                'occupied': len(bed_groups['occupied']),
                'reserved': len(bed_groups['reserved']),
                'free': len(bed_groups['free']),
                'unavailable': len(beds_unavailable),
                'to_clean': len(beds_to_clean),
            },
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
            'period': {
                'start': fields.Date.to_string(date_from),
                'end': fields.Date.to_string(date_to),
                'label': date_from.strftime('%d/%m/%Y') + ' – ' + date_to.strftime('%d/%m/%Y'),
                'days': period_days,
                'nights': period_nights,
                'capacity': all_active_beds * period_days,
                'bed_rate': round(period_nights / (all_active_beds * period_days) * 100, 1)
                if all_active_beds and period_days else 0.0,
            },
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
    # Location « par lit » : une ligne = un lit ; la chambre en est déduite.
    bed_id = fields.Many2one('hotel.bed', string="Lit", index=True)
    available_bed_ids = fields.Many2many(
        'hotel.bed', 'hotel_resline_avail_bed_rel', 'line_id', 'bed_id',
        string="Lits disponibles", compute='_compute_available_bed_ids',
        help="Lits libres de la chambre sur la période : seuls ceux-ci sont "
             "proposés à la sélection.")
    room_type_id = fields.Many2one(
        related='reservation_id.room_type_id', string="Type", store=True)
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
        saisonnier nuit par nuit, sinon prix du type de chambre (chambre, ou lit × nb lits)."""
        if not self.room_id:
            return
        resa = self.reservation_id
        unit = self.room_id._get_stay_unit_price(
            resa.checkin, resa.checkout, self.booking_type, resa.partner_id,
            resa.room_type_id)
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
        """Aligne les lits de la ligne sur le « Type de location » :
        chambre entière -> tous les lits de la chambre, obligatoirement ;
        par lit -> le lit choisi (sa chambre est déduite)."""
        if self.booking_type == 'room':
            self.bed_id = False
            self.bed_ids = [(6, 0, self.room_id.bed_ids.filtered('active').ids)]
        elif self.bed_id:
            self.room_id = self.bed_id.room_id
            self.bed_ids = [(6, 0, self.bed_id.ids)]
        self._apply_price()

    @api.onchange('room_id')
    def _onchange_room_id(self):
        if self.room_id and self.booking_type == 'room':
            self._apply_booking_type()

    @api.onchange('bed_id')
    def _onchange_bed_id(self):
        if self.bed_id:
            self._apply_booking_type()

    @api.model
    def _sync_beds_vals(self, vals, booking_type):
        """Mêmes règles qu'à l'écran pour les écritures directes (site web,
        import, code) : par chambre = tous les lits ; par lit = lit -> chambre."""
        if booking_type == 'bed' and vals.get('bed_id'):
            bed = self.env['hotel.bed'].browse(vals['bed_id'])
            vals['room_id'] = bed.room_id.id
            vals['bed_ids'] = [(6, 0, bed.ids)]
        return vals

    def _force_room_beds(self):
        """Par chambre : tous les lits actifs de la chambre sont réservés."""
        for line in self:
            if line.booking_type == 'room' and line.room_id:
                beds = line.room_id.bed_ids.filtered('active')
                if line.bed_ids != beds or line.bed_id:
                    super(HotelReservationLine, line).write(
                        {'bed_ids': [(6, 0, beds.ids)], 'bed_id': False})
            elif line.booking_type == 'bed' and not line.bed_id \
                    and len(line.bed_ids) == 1:
                super(HotelReservationLine, line).write({'bed_id': line.bed_ids.id})

    @api.model_create_multi
    def create(self, vals_list):
        Resa = self.env['hotel.reservation']
        for vals in vals_list:
            resa = Resa.browse(vals.get('reservation_id'))
            self._sync_beds_vals(vals, resa.booking_type if resa else 'bed')
        lines = super().create(vals_list)
        lines._force_room_beds()
        return lines

    def write(self, vals):
        if vals.get('bed_id'):
            types = set(self.mapped('booking_type'))
            if types == {'bed'}:
                vals = self._sync_beds_vals(dict(vals), 'bed')
        res = super().write(vals)
        if {'room_id', 'bed_ids', 'bed_id'} & set(vals):
            self._force_room_beds()
        return res

    @api.constrains('price_unit')
    def _check_price_unit(self):
        for line in self:
            if line.price_unit < 0:
                raise ValidationError(_(
                    "Le prix par nuit d'une chambre ne peut pas être négatif."))

    @api.constrains('room_id', 'reservation_id', 'bed_ids')
    def _check_unique_room_per_reservation(self):
        """Par chambre : une même chambre une seule fois par réservation.
        Par lit : un même lit une seule fois."""
        for line in self:
            if not (line.room_id and line.reservation_id):
                continue
            if line.booking_type == 'bed':
                # Par lit : une ligne par lit, un même lit une seule fois.
                twin = line.reservation_id.line_ids.filtered(
                    lambda l: l.id != line.id and l.bed_ids & line.bed_ids)
                if twin:
                    raise ValidationError(_(
                        "Le lit %(bed)s figure plusieurs fois dans la réservation %(res)s.",
                        bed=', '.join((twin.bed_ids & line.bed_ids).mapped('name')),
                        res=line.reservation_id.name))
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
