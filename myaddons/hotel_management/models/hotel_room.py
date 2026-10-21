from odoo import api, fields, models


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
    bed_capacity = fields.Integer(string="Nombre de lits max", default=3)
    bed_ids = fields.One2many('hotel.bed', 'room_id', string="Lits")
    bed_count = fields.Integer(string="Nb lits", compute='_compute_bed_count')
    image = fields.Image(string="Photo")
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)
    website_published = fields.Boolean(string="Publié sur le site", default=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    maintenance = fields.Boolean(string="En maintenance", tracking=True)
    housekeeping_status = fields.Selection([
        ('clean', 'Propre'),
        ('dirty', 'À nettoyer'),
        ('inprogress', 'Nettoyage en cours'),
    ], string="État ménage", default='clean', required=True, tracking=True)

    status = fields.Selection([
        ('available', 'Disponible'),
        ('occupied', 'Occupée'),
        ('maintenance', 'Maintenance'),
    ], string="Statut", compute='_compute_status')
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
            if self.room_type_id.amenity_ids:
                self.amenity_ids = [(6, 0, self.room_type_id.amenity_ids.ids)]

    @api.depends('bed_ids')
    def _compute_bed_count(self):
        for room in self:
            room.bed_count = len(room.bed_ids)

    def available_beds(self, checkin, checkout, ignore_reservation=False):
        """Lits actifs et libres de la chambre sur [checkin, checkout[."""
        self.ensure_one()
        return self.bed_ids.filtered(
            lambda b: b.active and b.is_available(
                checkin, checkout, ignore_reservation))

    def _compute_status(self):
        today = fields.Date.context_today(self)
        Line = self.env['hotel.reservation.line']
        for room in self:
            room.current_reservation_id = False
            room.current_guest_id = False
            if room.maintenance:
                room.status = 'maintenance'
                continue
            line = Line.search([
                ('room_id', '=', room.id),
                ('state', '=', 'checkin'),
                ('checkin', '<=', today),
                ('checkout', '>=', today),
            ], limit=1)
            if line:
                room.status = 'occupied'
                room.current_reservation_id = line.reservation_id
                room.current_guest_id = line.partner_id
            else:
                room.status = 'available'

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
            ('capacity', '>=', guests or 1),
        ])
        return rooms.filtered(lambda r: r.is_available(checkin, checkout))

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
