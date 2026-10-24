from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class HotelReservation(models.Model):
    _name = 'hotel.reservation'
    _description = "Réservation"
    _order = 'checkin desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=lambda self: _('Nouveau'))
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
    checkin = fields.Date(
        string="Arrivée", required=True, tracking=True,
        default=fields.Date.context_today)
    checkout = fields.Date(string="Départ", required=True, tracking=True)
    nights = fields.Integer(string="Nuits", compute='_compute_nights', store=True)
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
    deposit_amount = fields.Monetary(string="Acompte", tracking=True)
    amount_due = fields.Monetary(
        string="Reste à payer", compute='_compute_amount_due', store=True)
    invoice_ids = fields.One2many(
        'account.move', 'hotel_reservation_id', string="Factures")
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

    @api.depends('line_ids.price_subtotal')
    def _compute_amounts(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped('price_subtotal'))
            rec.room_count = len(rec.line_ids)

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

    @api.depends('amount_total', 'deposit_amount')
    def _compute_amount_due(self):
        for rec in self:
            rec.amount_due = rec.amount_total - rec.deposit_amount

    @api.constrains('deposit_amount')
    def _check_deposit_amount(self):
        for rec in self:
            if rec.deposit_amount < 0:
                raise ValidationError(_("L'acompte ne peut pas être négatif."))

    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    def _get_income_account(self):
        Account = self.env['account.account']
        account = Account.search([
            ('account_type', '=', 'income'),
            ('company_id', '=', self.company_id.id),
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
        income = self._get_income_account()
        if not income:
            raise UserError(_("Aucun compte de produits configuré dans la comptabilité."))
        move_lines = []
        for line in self.line_ids:
            if line.booking_type == 'bed' and line.bed_ids:
                label = _("Chambre %s — lit(s) %s — %s nuit(s)") % (
                    line.room_id.name,
                    ', '.join(line.bed_ids.mapped('name')), line.nights)
            else:
                label = _("Chambre %s — chambre entière — %s nuit(s)") % (
                    line.room_id.name, line.nights)
            move_lines.append((0, 0, {
                'name': label,
                'quantity': line.nights or 1,
                'price_unit': line.price_unit,
                'account_id': income.id,
            }))
        move = self.env['account.move'].sudo().create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_origin': self.name,
            'hotel_reservation_id': self.id,
            'invoice_line_ids': move_lines,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _("Facture"),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Factures"),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('hotel_reservation_id', '=', self.id)],
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
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Ajoutez au moins une chambre avant de confirmer."))
            rec._check_guest_places()
            rec._check_availability()
            rec.state = 'confirmed'

    def action_checkin(self):
        for rec in self:
            rec._check_guest_places()
            rec._check_availability()
            rec.state = 'checkin'

    def action_checkout(self):
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

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})

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

        by_type_groups = Room.read_group([], ['room_type_id'], ['room_type_id'])
        rooms_by_type = [{
            'name': g['room_type_id'][1] if g['room_type_id'] else _('Sans type'),
            'count': g['room_type_id_count'],
        } for g in by_type_groups]

        housekeeping_todo = self.env['hotel.housekeeping'].search_count([
            ('state', 'in', ('todo', 'inprogress'))])
        maintenance_open = self.env['hotel.maintenance.request'].search_count([
            ('state', 'in', ('new', 'inprogress'))])

        symbol = self.env.company.currency_id.symbol or ''
        return {
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
    booking_type = fields.Selection([
        ('room', 'Chambre entière'),
        ('bed', 'Lit(s)'),
    ], string="Mode de location", default='room', required=True)
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
        if self.booking_type == 'bed':
            self.price_unit = len(self.bed_ids) * self.room_id.bed_price
        elif self.room_id:
            self.price_unit = self.room_id.room_price

    @api.onchange('room_id')
    def _onchange_room_id(self):
        if not self.room_id:
            return
        active_beds = self.room_id.bed_ids.filtered('active')
        # Sans lit, seule la chambre entière est possible.
        if self.booking_type == 'bed' and not active_beds:
            self.booking_type = 'room'
        if self.booking_type == 'room':
            # Chambre entière : la ligne reprend tous les lits de la chambre.
            self.bed_ids = [(6, 0, active_beds.ids)]
        else:
            # Par lit : ne garder que les lits de cette chambre.
            self.bed_ids = self.bed_ids.filtered(lambda b: b.room_id == self.room_id)
        self._apply_price()

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
