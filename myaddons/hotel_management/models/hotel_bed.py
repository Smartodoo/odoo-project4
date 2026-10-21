from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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

    _sql_constraints = [
        ('name_room_uniq', 'unique(name, room_id)',
         "Cette référence de lit existe déjà dans cette chambre."),
    ]

    @api.depends('name', 'room_id.name')
    def _compute_display_name(self):
        for bed in self:
            if bed.room_id:
                bed.display_name = "%s (%s)" % (bed.name or '', bed.room_id.name)
            else:
                bed.display_name = bed.name or ''

    @api.constrains('room_id')
    def _check_bed_capacity(self):
        for bed in self:
            room = bed.room_id
            if room and room.bed_capacity and len(room.bed_ids) > room.bed_capacity:
                raise ValidationError(_(
                    "La chambre %s ne peut pas avoir plus de %s lit(s).",
                    room.name, room.bed_capacity))

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
