from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class HotelBed(models.Model):
    _name = 'hotel.bed'
    _description = "Lit"
    _order = 'room_id, name'

    name = fields.Char(string="Référence", required=True)
    room_id = fields.Many2one(
        'hotel.room', string="Chambre", required=True, ondelete='cascade')
    room_type_id = fields.Many2one(
        related='room_id.room_type_id', string="Type", store=True)
    price = fields.Monetary(string="Prix / nuit", currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', related='room_id.currency_id', store=True)
    active = fields.Boolean(default=True)
    website_published = fields.Boolean(
        related='room_id.website_published', string="Publié", store=True)
    company_id = fields.Many2one(
        'res.company', related='room_id.company_id', store=True)
    status = fields.Selection([
        ('free', 'Libre'),
        ('reserved', 'Réservé'),
        ('occupied', 'Occupé'),
        ('maintenance', 'Maintenance'),
        ('out_of_service', 'Hors service'),
    ], string="Statut", compute='_compute_status')
    current_guest_id = fields.Many2one(
        'res.partner', string="Client", compute='_compute_status')

    _sql_constraints = [
        ('name_room_uniq', 'unique(name, room_id)',
         "Cette référence de lit existe déjà dans cette chambre."),
    ]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        room_id = res.get('room_id') or self.env.context.get('default_room_id')
        room = self.env['hotel.room'].browse(room_id).exists()
        if room:
            if 'name' in fields_list and not res.get('name'):
                taken = set(room.with_context(active_test=False).bed_ids.mapped('name'))
                res['name'] = room._next_bed_reference(taken)
            if 'price' in fields_list and not res.get('price'):
                res['price'] = room._default_bed_price()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_reserved(self):
        lines = self.env['hotel.reservation.line'].search([('bed_ids', 'in', self.ids)])
        reserved = lines.mapped('bed_ids') & self
        if reserved:
            raise UserError(_(
                "Le(s) lit(s) %s figure(nt) dans des réservations et ne peuvent "
                "pas être supprimés. Désactivez-les plutôt (colonne « Actif »).",
                ', '.join(reserved.mapped('display_name'))))

    @api.depends('name', 'room_id.name')
    def _compute_display_name(self):
        for bed in self:
            if bed.room_id:
                bed.display_name = "%s (%s)" % (bed.name or '', bed.room_id.name)
            else:
                bed.display_name = bed.name or ''

    def _compute_status(self):
        today = fields.Date.context_today(self)
        occupation = {}
        for room in self.mapped('room_id'):
            occupation.update(room._get_bed_occupation(today))
        for bed in self:
            line = occupation.get(bed)
            bed.current_guest_id = line.partner_id if line else False
            if bed.room_id.maintenance:
                bed.status = bed.room_id.technical_state
            elif not line:
                bed.status = 'free'
            else:
                bed.status = 'occupied' if line.state == 'checkin' else 'reserved'

    @api.constrains('room_id')
    def _check_bed_capacity(self):
        for bed in self:
            room = bed.room_id
            if room and room.bed_capacity and len(room.bed_ids) > room.bed_capacity:
                raise ValidationError(_(
                    "La chambre %(room)s est limitée à %(limit)s lit(s), mais vous "
                    "essayez d'en avoir %(total)s.\n\n"
                    "Lits déjà enregistrés : %(existing)s.\n\n"
                    "Solutions : supprimez ou désactivez des lits, ou augmentez la "
                    "« Limite de lits » de la chambre.",
                    room=room.name, limit=room.bed_capacity,
                    total=len(room.bed_ids),
                    existing=', '.join(
                        (room.bed_ids - self).mapped('name')) or '-'))

    def is_available(self, checkin, checkout, ignore_reservation=False):
        """True si le lit est libre sur [checkin, checkout[ : aucune réservation
        « chambre entière » ni « lit » chevauchante ne le mobilise."""
        self.ensure_one()
        if self.room_id.maintenance:
            return False
        domain = [
            ('room_id', '=', self.room_id.id),
            ('state', 'in', ('confirmed', 'checkin')),
            ('checkin', '<', checkout),
            ('checkout', '>', checkin),
        ]
        if ignore_reservation:
            domain.append(('reservation_id', '!=', ignore_reservation.id))
        lines = self.env['hotel.reservation.line'].search(domain)
        for line in lines:
            if line.booking_type == 'room' or self in line.bed_ids:
                return False
        return True
