from markupsafe import Markup, escape

from odoo import _, api, fields, models


class HotelRoom(models.Model):
    _name = 'hotel.room'
    _description = "Chambre"
    _order = 'name'
    _inherit = ['mail.thread']

    name = fields.Char(string="Numéro / Nom", required=True, tracking=True)
    room_type_id = fields.Many2one(
        'hotel.room.type', string="Type", required=True, tracking=True)
    floor = fields.Char(string="Étage")
    capacity = fields.Integer(string="Capacité", default=2)
    price = fields.Monetary(string="Prix / nuit", currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    amenity_ids = fields.Many2many('hotel.amenity', string="Équipements")
    bed_capacity = fields.Integer(
        string="Limite de lits", default=0,
        help="Nombre maximum de lits dans la chambre. 0 = pas de limite.")
    bed_ids = fields.One2many('hotel.bed', 'room_id', string="Lits")
    bed_count = fields.Integer(string="Nb lits", compute='_compute_bed_count')
    bed_summary = fields.Char(string="Lits créés", compute='_compute_bed_count')
    image = fields.Image(string="Photo")
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)
    website_published = fields.Boolean(string="Publié sur le site", default=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    technical_state = fields.Selection([
        ('in_service', 'En service'),
        ('maintenance', 'Maintenance'),
        ('out_of_service', 'Hors service'),
    ], string="État technique", default='in_service', required=True, tracking=True,
        help="Maintenance : réparation temporaire.\n"
             "Hors service : chambre fermée durablement (travaux, non aménagée).\n"
             "Dans les deux cas, la chambre n'est pas vendable.")
    maintenance = fields.Boolean(
        string="Indisponible", compute='_compute_maintenance', store=True,
        help="Chambre en maintenance ou hors service : non vendable.")
    housekeeping_status = fields.Selection([
        ('clean', 'Propre'),
        ('dirty', 'À nettoyer'),
        ('inprogress', 'Nettoyage en cours'),
    ], string="État ménage", default='clean', required=True, tracking=True)

    # Mode de location : chambre privée, dortoir (au lit) ou mixte
    rental_mode = fields.Selection([
        ('room', 'Chambre entière uniquement'),
        ('bed', 'Au lit uniquement (dortoir)'),
        ('both', 'Chambre entière ou au lit'),
    ], string="Mode de location", default='both', required=True, tracking=True,
        help="Chambre entière : la chambre se loue à un seul client.\n"
             "Au lit : chaque lit se loue séparément (dortoir).\n"
             "Les deux : le client choisit la chambre entière ou un/des lit(s).")
    whole_room_pricing = fields.Selection([
        ('sum_beds', 'Somme des prix des lits'),
        ('fixed', 'Prix fixe de la chambre'),
    ], string="Prix chambre entière", default='sum_beds', required=True,
        tracking=True,
        help="Somme des lits : 3 lits à 2000 DA = 6000 DA la nuit.\n"
             "Prix fixe : le champ « Prix / nuit » (tarifs saisonniers inclus).")
    whole_room_price = fields.Monetary(
        string="Prix chambre entière / nuit", currency_field='currency_id',
        compute='_compute_whole_room_price')
    bed_price_min = fields.Monetary(
        string="Prix lit à partir de", currency_field='currency_id',
        compute='_compute_whole_room_price')

    status = fields.Selection([
        ('available', 'Libre'),
        ('partial', 'Partiellement occupée'),
        ('reserved', 'Réservée'),
        ('occupied', 'Complète'),
        ('cleaning', 'Nettoyage'),
        ('maintenance', 'Maintenance'),
        ('out_of_service', 'Hors service'),
    ], string="Statut", compute='_compute_status')
    beds_free_count = fields.Integer(string="Lits libres", compute='_compute_status')
    bed_availability = fields.Char(string="Disponibilité lits", compute='_compute_status')
    bed_map = fields.Html(string="Plan des lits", compute='_compute_status', sanitize=False)
    current_reservation_id = fields.Many2one(
        'hotel.reservation', string="Réservation en cours", compute='_compute_status')
    current_guest_id = fields.Many2one(
        'res.partner', string="Client présent", compute='_compute_status')

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)',
         "Ce numéro de chambre existe déjà."),
    ]

    @api.onchange('room_type_id')
    def _onchange_room_type_id(self):
        if self.room_type_id:
            if not self.price:
                self.price = self.room_type_id.list_price
            if not self.capacity:
                self.capacity = self.room_type_id.default_capacity
            self.rental_mode = self.room_type_id.rental_mode
            if self.room_type_id.amenity_ids:
                self.amenity_ids = [(6, 0, self.room_type_id.amenity_ids.ids)]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'rental_mode' not in vals and vals.get('room_type_id'):
                vals['rental_mode'] = self.env['hotel.room.type'].browse(
                    vals['room_type_id']).rental_mode
        return super().create(vals_list)

    @api.depends('bed_ids', 'bed_capacity')
    def _compute_bed_count(self):
        for room in self:
            room.bed_count = len(room.bed_ids)
            if room.bed_capacity:
                room.bed_summary = "%s / %s" % (room.bed_count, room.bed_capacity)
            else:
                room.bed_summary = str(room.bed_count)

    def _next_bed_reference(self, taken):
        """Première référence libre de la forme <chambre>-L<n>."""
        self.ensure_one()
        n = 1
        while "%s-L%s" % (self.name, n) in taken:
            n += 1
        return "%s-L%s" % (self.name, n)

    def _default_bed_price(self):
        self.ensure_one()
        return self.price or self.room_type_id.list_price

    def _number_new_beds(self, beds):
        """Numérote les nouveaux lits d'un formulaire : plusieurs lignes ajoutées
        avant l'enregistrement reçoivent sinon la même référence par défaut."""
        self.ensure_one()
        taken = set(self.env['hotel.bed'].with_context(active_test=False).search(
            [('room_id', '=', self._origin.id)]).mapped('name'))
        taken |= set(beds.filtered(lambda b: b._origin).mapped('name'))
        for bed in beds.filtered(lambda b: not b._origin):
            if not bed.name or bed.name in taken:
                bed.name = self._next_bed_reference(taken)
            taken.add(bed.name)
            if not bed.price:
                bed.price = self._default_bed_price()

    @api.onchange('bed_ids')
    def _onchange_bed_ids_reference(self):
        self._number_new_beds(self.bed_ids)
        if self.bed_capacity and len(self.bed_ids) > self.bed_capacity:
            return {'warning': {
                'title': _("Limite de lits dépassée"),
                'message': _(
                    "Cette chambre est limitée à %(limit)s lit(s) et la liste en "
                    "contient %(count)s. Supprimez des lignes ou augmentez la "
                    "« Limite de lits », sinon l'enregistrement sera refusé.",
                    limit=self.bed_capacity, count=len(self.bed_ids)),
            }}

    def action_manage_beds(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Lits"),
            'res_model': 'hotel.room',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('hotel_management.view_hotel_room_beds_form').id, 'form')],
            'target': 'current',
        }

    def available_beds(self, checkin, checkout, ignore_reservation=False):
        """Lits actifs et libres de la chambre sur [checkin, checkout[."""
        self.ensure_one()
        return self.bed_ids.filtered(
            lambda b: b.active and b.is_available(
                checkin, checkout, ignore_reservation))

    @api.depends('technical_state')
    def _compute_maintenance(self):
        for room in self:
            room.maintenance = room.technical_state != 'in_service'

    @api.depends('rental_mode', 'whole_room_pricing', 'price',
                 'bed_ids.price', 'bed_ids.active', 'room_type_id.list_price')
    def _compute_whole_room_price(self):
        for room in self:
            room.whole_room_price = room._get_whole_room_price(False)
            prices = room.bed_ids.filtered('active').mapped('price')
            room.bed_price_min = min(prices) if prices else 0.0

    def _get_whole_room_price(self, day):
        """Prix/nuit de la chambre entière selon la politique choisie."""
        self.ensure_one()
        beds = self.bed_ids.filtered('active')
        if self.whole_room_pricing == 'sum_beds' and beds:
            return sum(beds.mapped('price'))
        return self._get_price_for_date(day)

    def _get_active_lines(self, day):
        """Lignes de réservation qui mobilisent la chambre le jour donné.
        Un client enregistré reste présent jusqu'à son check-out effectif."""
        self.ensure_one()
        lines = self.env['hotel.reservation.line'].search([
            ('room_id', '=', self.id),
            ('state', 'in', ('confirmed', 'checkin')),
            ('checkin', '<=', day),
            ('checkout', '>=', day),
        ], order='checkin')
        return lines.filtered(lambda l: l.checkout > day or l.state == 'checkin')

    def _get_bed_occupation(self, day):
        """{lit: ligne de réservation} des lits mobilisés le jour donné."""
        self.ensure_one()
        beds = self.bed_ids.filtered('active')
        taken = {}
        for line in self._get_active_lines(day):
            line_beds = beds if line.booking_type == 'room' else line.bed_ids
            for bed in line_beds:
                # Un client présent prime sur une simple réservation
                if bed not in taken or line.state == 'checkin':
                    taken[bed] = line
        return taken

    def _compute_status(self):
        today = fields.Date.context_today(self)
        for room in self:
            beds = room.bed_ids.filtered('active')
            lines = room._get_active_lines(today)
            taken = room._get_bed_occupation(today)
            whole = lines.filtered(lambda l: l.booking_type == 'room')
            current = (lines.filtered(lambda l: l.state == 'checkin') or lines)[:1]

            room.current_reservation_id = current.reservation_id
            room.current_guest_id = current.partner_id
            room.beds_free_count = len(beds) - len(taken)
            room.bed_availability = (
                "%s / %s lits libres" % (room.beds_free_count, len(beds))
                if beds else "")
            room.bed_map = room._render_bed_map(beds, taken)

            if room.maintenance:
                room.status = room.technical_state
            elif not lines:
                # Le ménage est signalé mais ne bloque pas la vente
                room.status = ('cleaning' if room.housekeeping_status != 'clean'
                               else 'available')
            elif whole or (beds and len(taken) >= len(beds)) or not beds:
                checked_in = lines.filtered(lambda l: l.state == 'checkin')
                room.status = 'occupied' if checked_in else 'reserved'
            else:
                room.status = 'partial'

    def _render_bed_map(self, beds, taken):
        """Pastilles colorées, une par lit (vert libre, bleu réservé, rouge occupé)."""
        if not beds:
            return False
        chips = []
        for bed in beds:
            line = taken.get(bed)
            if self.maintenance:
                css = 'maintenance'
                label = dict(self._fields['technical_state'].selection)[
                    self.technical_state]
            elif not line:
                css, label = 'free', "Libre"
            elif line.state == 'checkin':
                css, label = 'occupied', "Occupé — %s" % line.partner_id.name
            else:
                css, label = 'reserved', "Réservé — %s" % line.partner_id.name
            chips.append(Markup(
                '<span class="o_hotel_bed_chip o_hotel_bed_chip_%s" title="%s">'
                '<i class="fa fa-bed"></i> %s</span>') % (
                    css, escape(label), escape(bed.name)))
        return Markup('<div class="o_hotel_bed_map">%s</div>') % Markup('').join(chips)

    def can_book_whole_room(self, checkin, checkout, ignore_reservation=False):
        """La chambre entière peut-elle être louée sur la période ?"""
        self.ensure_one()
        return self.rental_mode != 'bed' and self.is_available(
            checkin, checkout, ignore_reservation)

    def bookable_beds(self, checkin, checkout, ignore_reservation=False):
        """Lits louables individuellement sur la période."""
        self.ensure_one()
        if self.rental_mode == 'room':
            return self.env['hotel.bed']
        return self.available_beds(checkin, checkout, ignore_reservation)

    def _get_price_for_date(self, day):
        """Prix/nuit applicable : tarif saisonnier prioritaire (spécifique au type,
        sinon global), à défaut le prix de la chambre ou de son type."""
        self.ensure_one()
        fallback = self.price or self.room_type_id.list_price
        if not day:
            return fallback
        Season = self.env['hotel.rate.season']
        base = [('date_start', '<=', day), ('date_end', '>=', day), ('active', '=', True)]
        season = Season.search(
            base + [('room_type_id', '=', self.room_type_id.id)], limit=1)
        if not season:
            season = Season.search(base + [('room_type_id', '=', False)], limit=1)
        return season.price if season else fallback

    @api.model
    def get_available_rooms(self, checkin, checkout, guests=1):
        """Chambres publiées, libres sur [checkin, checkout[ et assez grandes."""
        rooms = self.search([
            ('website_published', '=', True),
            ('maintenance', '=', False),
        ])
        return rooms.filtered(lambda r: r.get_offer(checkin, checkout, guests)['bookable'])

    def get_offer(self, checkin, checkout, guests=1):
        """Ce que la chambre peut proposer sur la période : chambre entière
        et/ou lits libres, avec les prix correspondants."""
        self.ensure_one()
        guests = guests or 1
        whole = (self.capacity >= guests
                 and self.can_book_whole_room(checkin, checkout))
        beds = self.bookable_beds(checkin, checkout)
        beds_ok = len(beds) >= guests
        return {
            'whole': whole,
            'whole_price': self._get_whole_room_price(checkin),
            'beds': beds,
            'beds_ok': beds_ok,
            'bed_price_min': min(beds.mapped('price')) if beds else 0.0,
            'bookable': whole or beds_ok,
        }

    def is_available(self, checkin, checkout, ignore_reservation=False):
        """Renvoie True si la chambre est libre sur la période [checkin, checkout[."""
        self.ensure_one()
        if self.maintenance:
            return False
        domain = [
            ('room_id', '=', self.id),
            ('state', 'in', ('confirmed', 'checkin')),
            ('checkin', '<', checkout),
            ('checkout', '>', checkin),
        ]
        if ignore_reservation:
            domain.append(('reservation_id', '!=', ignore_reservation.id))
        return not self.env['hotel.reservation.line'].search_count(domain)
