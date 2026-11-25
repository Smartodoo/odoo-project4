from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .hotel_room import hotel_proposal_name_search


class HotelBed(models.Model):
    _name = 'hotel.bed'
    _description = "Lit"
    _order = 'room_id, name'

    name = fields.Char(string="Référence", required=True)
    room_id = fields.Many2one(
        'hotel.room', string="Chambre", required=True, ondelete='cascade')
    # Prix fixé par le type de chambre de la réservation : « à partir de »
    price = fields.Monetary(
        string="Prix / nuit (à partir de)", currency_field='currency_id',
        related='room_id.bed_price')
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
        ('cleaning', 'En nettoyage'),
        ('maintenance', 'Maintenance'),
        ('out_of_service', 'Hors service'),
    ], string="Statut", compute='_compute_status')
    current_guest_id = fields.Many2one(
        'res.partner', string="Client", compute='_compute_status')
    # État du ménage du lit (même cycle que la chambre)
    housekeeping_status = fields.Selection([
        ('dirty', 'À nettoyer'),
        ('inprogress', 'En nettoyage'),
        ('clean', 'Nettoyé'),
        ('inspected', 'Contrôlé'),
        ('to_repair', 'À réparer'),
    ], string="État ménage", default='clean', required=True)
    housekeeping_count = fields.Integer(
        string="Ménages", compute='_compute_housekeeping_count')

    def _compute_housekeeping_count(self):
        groups = self.env['hotel.housekeeping']._read_group(
            [('bed_ids', 'in', self.ids)], ['bed_ids'], ['__count'])
        counts = {bed.id: count for bed, count in groups}
        for bed in self:
            bed.housekeeping_count = counts.get(bed.id, 0)

    def action_view_housekeeping(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Housekeeping — lit %s", self.display_name),
            'res_model': 'hotel.housekeeping',
            'view_mode': 'list,form',
            'domain': [('bed_ids', 'in', self.ids)],
            'context': {'default_room_id': self.room_id.id,
                        'default_target': 'bed',
                        'default_bed_ids': [(6, 0, self.ids)]},
        }

    def action_create_housekeeping(self):
        """Bouton « Ménage » de la liste des lits : une tâche pour les lits
        sélectionnés, une par chambre."""
        Housekeeping = self.env['hotel.housekeeping']
        tasks = Housekeeping
        for room in self.room_id:
            tasks |= Housekeeping.create({
                'room_id': room.id,
                'target': 'bed',
                'bed_ids': [(6, 0, self.filtered(lambda b: b.room_id == room).ids)],
                'cleaning_type': 'other',
            })
        return {
            'type': 'ir.actions.act_window',
            'name': _("Housekeeping des lits"),
            'res_model': 'hotel.housekeeping',
            'view_mode': 'list,form',
            'domain': [('id', 'in', tasks.ids)],
        }

    _name_room_uniq = models.Constraint(
        'unique(name, room_id)',
        "Cette r\u00e9f\u00e9rence de lit existe d\u00e9j\u00e0 dans cette chambre.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        room_id = res.get('room_id') or self.env.context.get('default_room_id')
        room = self.env['hotel.room'].browse(room_id).exists()
        if room:
            if 'name' in fields_list and not res.get('name'):
                taken = set(room.with_context(active_test=False).bed_ids.mapped('name'))
                res['name'] = room._next_bed_reference(taken)
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

    @api.model
    @api.readonly
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        ordered = hotel_proposal_name_search(self, name, domain, operator, limit)
        if ordered is not None:
            return ordered
        return super().name_search(name, domain, operator, limit)

    @api.depends('name', 'room_id.name')
    def _compute_display_name(self):
        for bed in self:
            if bed.room_id:
                bed.display_name = "%s (%s)" % (bed.name or '', bed.room_id.name)
            else:
                bed.display_name = bed.name or ''

    @api.depends('housekeeping_status')
    def _compute_status(self):
        today = fields.Date.context_today(self)
        occupation = {}
        for room in self.mapped('room_id'):
            occupation.update(room._get_bed_occupation(today))
        for bed in self:
            line = occupation.get(bed)
            bed.current_guest_id = line.partner_id if line else False
            if bed.room_id.maintenance:
                # cf. hotel.room._compute_status : maintenance forcée sans
                # changer technical_state (qui peut rester 'in_service').
                bed.status = (bed.room_id.technical_state
                              if bed.room_id.technical_state != 'in_service'
                              else 'maintenance')
            elif not line:
                # Comme la chambre : le ménage est signalé mais ne bloque pas la vente
                bed.status = ('cleaning' if bed.housekeeping_status
                              not in ('clean', 'inspected') else 'free')
            else:
                bed.status = 'occupied' if line.state == 'checkin' else 'reserved'

    @api.constrains('room_id')
    def _check_bed_capacity(self):
        for bed in self:
            room = bed.room_id
            if room and room.capacity and len(room.bed_ids) > room.capacity:
                raise ValidationError(_(
                    "La chambre %(room)s a une capacité de %(limit)s lit(s), mais vous "
                    "essayez d'en avoir %(total)s.\n\n"
                    "Lits déjà enregistrés : %(existing)s.\n\n"
                    "Solutions : supprimez ou désactivez des lits, ou augmentez la "
                    "« Capacité » de la chambre.",
                    room=room.name, limit=room.capacity,
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
            ('state', 'in', self.room_id._hotel_blocking_states()),
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
