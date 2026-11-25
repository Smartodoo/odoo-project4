import re
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain


def hotel_proposal_name_search(model, name, domain, operator, limit):
    """Liste de choix d'une réservation : les propositions arrivent dans
    l'ordre calculé par la réservation (contexte « hotel_proposal_order » =
    ids séparés par des virgules) au lieu de l'ordre alphabétique.
    Renvoie None hors de ce contexte."""
    order = model.env.context.get('hotel_proposal_order')
    if not order or not isinstance(order, str):
        return None
    ids = [int(x) for x in order.split(',') if x.strip().isdigit()]
    rank = {rid: n for n, rid in enumerate(ids)}
    search_domain = Domain('display_name', operator, name) & Domain(domain or Domain.TRUE)
    records = model.search_fetch(search_domain, ['display_name'])
    records = records.sorted(lambda r: (rank.get(r.id, len(rank)), r.display_name or ''))
    if limit:
        records = records[:limit]
    return [(r.id, r.display_name) for r in records.sudo()]

# Capacité maximale d'une chambre (nombre de places / lits)
MAX_ROOM_CAPACITY = 3


class HotelRoom(models.Model):
    _name = 'hotel.room'
    _description = "Chambre"
    _order = 'name'
    _inherit = ['mail.thread']

    name = fields.Char(string="Numéro / Nom", required=True, tracking=True)
    floor_id = fields.Many2one(
        'hotel.floor', string="Étage", ondelete='restrict', index=True,
        help="Étages saisis dans Configuration > Étages.")
    # Nom de l'étage (site web, planning, rapports, tri)
    floor = fields.Char(related='floor_id.name', string="Étage (nom)", store=True)
    capacity = fields.Integer(string="Capacité", default=3, tracking=True)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    amenity_ids = fields.Many2many('hotel.amenity', string="Équipements")
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
    # Cycle ménage (cahier des charges §14) :
    # À nettoyer -> En nettoyage -> Nettoyée -> Contrôlée ; À réparer si un
    # problème est signalé pendant le ménage.
    housekeeping_status = fields.Selection([
        ('dirty', 'À nettoyer'),
        ('inprogress', 'En nettoyage'),
        ('clean', 'Nettoyée'),
        ('inspected', 'Contrôlée'),
        ('to_repair', 'À réparer'),
    ], string="État ménage", default='clean', required=True, tracking=True)

    # Les prix sont portés par les types de chambre (choisi dans la
    # réservation) : sur la chambre, simple « à partir de » (site web, tri).
    whole_room_price = fields.Monetary(
        string="Prix chambre à partir de", currency_field='currency_id',
        compute='_compute_whole_room_price')
    bed_price_min = fields.Monetary(
        string="Prix lit à partir de", currency_field='currency_id',
        compute='_compute_whole_room_price')
    room_price = fields.Monetary(
        string="Prix chambre (à partir de)", currency_field='currency_id',
        compute='_compute_whole_room_price')
    bed_price = fields.Monetary(
        string="Prix lit (à partir de)", currency_field='currency_id',
        compute='_compute_whole_room_price')

    status = fields.Selection([
        ('available', 'Disponible'),
        ('reserved', 'Réservé'),
        ('partial', 'Occupé partiellement'),
        ('occupied', 'Occupé complètement'),
        ('cleaning', 'En nettoyage'),
        ('maintenance', 'En maintenance'),
        ('out_of_service', 'Hors service'),
    ], string="Statut", compute='_compute_status')
    beds_free_count = fields.Integer(string="Lits libres", compute='_compute_status')
    bed_availability = fields.Char(string="Disponibilité lits", compute='_compute_status')
    bed_map = fields.Html(string="Plan des lits", compute='_compute_status', sanitize=False)
    current_reservation_id = fields.Many2one(
        'hotel.reservation', string="Réservation en cours", compute='_compute_status')
    current_guest_id = fields.Many2one(
        'res.partner', string="Client présent", compute='_compute_status')
    current_guest_ids = fields.Many2many(
        'res.partner', string="Clients présents", compute='_compute_status',
        help="Tous les clients des réservations en cours sur cette chambre.")

    # Mode de location et montant de la RÉSERVATION EN COURS (lecture seule) :
    # le mode n'est plus réglé sur la chambre mais choisi dans la réservation.
    current_booking_type = fields.Selection([
        ('room', 'Chambre entière'),
        ('bed', 'Au lit'),
    ], string="Mode (réservation en cours)", compute='_compute_status')
    current_rental_amount = fields.Monetary(
        string="Montant (réservation en cours)", currency_field='currency_id',
        compute='_compute_status',
        help="Prix / nuit de la réservation en cours sur cette chambre.")
    # Montants des réservations actives (confirmées ou enregistrées) de la
    # chambre, quelle que soit la date : part de la chambre dans chaque séjour.
    current_reservation_total = fields.Monetary(
        string="Total réservations en cours", currency_field='currency_id',
        compute='_compute_reservation_totals',
        help="Montant prévu pour cette chambre (prix / nuit x nuits), toutes "
             "réservations confirmées ou enregistrées confondues.")
    current_reservation_paid = fields.Monetary(
        string="Encaissé (réservations en cours)", currency_field='currency_id',
        compute='_compute_reservation_totals',
        help="Acomptes versés, répartis au prorata quand une réservation "
             "porte sur plusieurs chambres.")
    current_reservation_due = fields.Monetary(
        string="Reste à encaisser", currency_field='currency_id',
        compute='_compute_reservation_totals')
    current_reservation_paid_pct = fields.Float(
        string="% encaissé", compute='_compute_reservation_totals')
    current_reservation_count = fields.Integer(
        string="Nb réservations en cours", compute='_compute_reservation_totals')

    # Compteurs pour les boutons de la fiche chambre
    reservation_count = fields.Integer(
        string="Nb réservations", compute='_compute_operation_counts')
    housekeeping_count = fields.Integer(
        string="Nb tâches ménage", compute='_compute_operation_counts')
    maintenance_count = fields.Integer(
        string="Nb demandes travaux", compute='_compute_operation_counts')

    _name_company_uniq = models.Constraint(
        'unique(name, company_id)',
        "Ce num\u00e9ro de chambre existe d\u00e9j\u00e0.",
    )
    _capacity_positive = models.Constraint(
        'CHECK(capacity > 0)',
        "La capacit\u00e9 d'une chambre doit \u00eatre d'au moins 1 personne.",
    )
    @api.constrains('capacity')
    def _check_capacity_max(self):
        for room in self:
            if room.capacity > MAX_ROOM_CAPACITY:
                raise ValidationError(_(
                    "La chambre %(room)s ne peut pas dépasser %(max)s places "
                    "(capacité saisie : %(capacity)s).",
                    room=room.name, max=MAX_ROOM_CAPACITY, capacity=room.capacity))

    @api.model_create_multi
    def create(self, vals_list):
        rooms = super().create(vals_list)
        if not self.env.context.get('hotel_no_auto_beds'):
            rooms._create_missing_beds()
        return rooms

    def write(self, vals):
        old_names = {room.id: room.name for room in self} if 'name' in vals else {}
        res = super().write(vals)
        if old_names:
            self._rename_beds(old_names)
        if 'capacity' in vals and not self.env.context.get('hotel_no_auto_beds'):
            self._create_missing_beds()
            self._remove_extra_beds()
        return res

    def _rename_beds(self, old_names):
        """Chambre renommée : <ancien>-L<n> devient <nouveau>-L<n>. Les lits
        nommés à la main ne sont pas modifiés."""
        for room in self:
            old = old_names.get(room.id)
            if not old or old == room.name:
                continue
            pattern = re.compile(r'^%s-L(\d+)$' % re.escape(old))
            for bed in room.with_context(active_test=False).bed_ids:
                match = pattern.match(bed.name or '')
                if match:
                    bed.name = "%s-L%s" % (room.name, match.group(1))

    @staticmethod
    def _bed_number(bed):
        match = re.search(r'-L(\d+)$', bed.name or '')
        return int(match.group(1)) if match else 0

    def _remove_extra_beds(self):
        """Baisse de capacité : retire les lits actifs en trop, en commençant par
        les numéros les plus élevés. Lit jamais réservé -> supprimé ; lit présent
        seulement dans des réservations passées / annulées -> archivé (historique
        conservé). Lit pris par une réservation en cours ou à venir -> refus."""
        today = fields.Date.context_today(self)
        Line = self.env['hotel.reservation.line']
        for room in self:
            beds = room.bed_ids
            extra = len(beds) - (room.capacity or 0)
            if extra <= 0:
                continue
            lines = Line.search([('bed_ids', 'in', beds.ids)])
            busy = lines.filtered(
                lambda l: l.state in ('draft', 'confirmed', 'checkin')
                and l.checkout and l.checkout > today).bed_ids & beds
            used = lines.bed_ids & beds
            candidates = (beds - busy).sorted(
                lambda b: (-self._bed_number(b), -b.id))
            if len(candidates) < extra:
                raise UserError(_(
                    "Impossible de ramener la chambre %(room)s à %(capacity)s place(s) : "
                    "les lits %(beds)s sont pris par des réservations en cours ou à venir.\n\n"
                    "Modifiez ou annulez ces réservations, ou gardez une capacité plus élevée.",
                    room=room.name, capacity=room.capacity,
                    beds=', '.join(busy.mapped('name'))))
            to_remove = candidates[:extra]
            (to_remove & used).write({'active': False})
            (to_remove - used).unlink()

    def _onchange_topup_beds(self):
        """Chambre existante : ajuste les lits non encore enregistrés à la capacité
        (ajout de <chambre>-L<n>, ou retrait des lignes ajoutées en trop)."""
        capacity = self.capacity or 0
        new_beds = self.bed_ids.filtered(lambda b: not b._origin)
        extra = len(self.bed_ids) - capacity
        if extra > 0:
            if new_beds:
                self.bed_ids -= new_beds[-extra:]
            remaining = len(self.bed_ids) - capacity
            if remaining > 0:
                return {'warning': {
                    'title': _("Baisse de capacité"),
                    'message': _(
                        "%(count)s lit(s) en trop seront retirés à l'enregistrement "
                        "(numéros les plus élevés ; les lits ayant un historique de "
                        "réservation sont archivés).", count=remaining),
                }}
        elif extra < 0:
            taken = set(self.env['hotel.bed'].with_context(active_test=False).search(
                [('room_id', '=', self._origin.id)]).mapped('name'))
            taken |= set(self.bed_ids.mapped('name'))
            commands = []
            for _i in range(-extra):
                name = self._next_bed_reference(taken)
                taken.add(name)
                commands.append(Command.create({'name': name}))
            self.bed_ids = commands

    def _create_missing_beds(self):
        """Crée automatiquement les lits manquants jusqu'à la capacité de la
        chambre, nommés <chambre>-L<n> (référence modifiable ensuite)."""
        # renommages de lits encore en attente : à écrire avant les INSERT
        # (contrainte unique(name, room_id)).
        self.env['hotel.bed'].flush_model(['name', 'room_id'])
        bed_vals = []
        for room in self:
            existing = room.with_context(active_test=False).bed_ids
            missing = (room.capacity or 0) - len(room.bed_ids)
            if missing <= 0:
                continue
            taken = set(existing.mapped('name'))
            for _i in range(missing):
                name = room._next_bed_reference(taken)
                taken.add(name)
                bed_vals.append({'room_id': room.id, 'name': name})
        if bed_vals:
            self.env['hotel.bed'].create(bed_vals)

    def action_set_out_of_service(self):
        """Fermer durablement la chambre (statut « Hors service »)."""
        self.write({'technical_state': 'out_of_service'})

    def action_set_in_service(self):
        """Rouvrir une chambre hors service / en maintenance."""
        self.write({'technical_state': 'in_service'})

    @api.depends('bed_ids', 'capacity')
    def _compute_bed_count(self):
        for room in self:
            room.bed_count = len(room.bed_ids)
            if room.capacity:
                room.bed_summary = "%s / %s" % (room.bed_count, room.capacity)
            else:
                room.bed_summary = str(room.bed_count)

    def _next_bed_reference(self, taken):
        """Première référence libre de la forme <chambre>-L<n>."""
        self.ensure_one()
        n = 1
        while "%s-L%s" % (self.name, n) in taken:
            n += 1
        return "%s-L%s" % (self.name, n)

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

    @api.onchange('capacity', 'name')
    def _onchange_auto_beds(self):
        """Nouvelle chambre : pré-remplit l'onglet « Lits » avec un lit par place
        (<chambre>-L<n>). Les lits renommés à la main sont conservés.
        Chambre existante : une hausse de capacité ajoute les lits manquants."""
        if not self.name:
            return
        if self._origin.id:
            return self._onchange_topup_beds()
        auto = re.compile(r'.+-L\d+$')
        custom = self.bed_ids.filtered(lambda b: not auto.match(b.name or ''))
        commands = [Command.clear()] + [
            Command.create({'name': b.name}) for b in custom]
        taken = set(custom.mapped('name'))
        for _i in range(max((self.capacity or 0) - len(custom), 0)):
            name = self._next_bed_reference(taken)
            taken.add(name)
            commands.append(Command.create({'name': name}))
        self.bed_ids = commands

    @api.onchange('bed_ids')
    def _onchange_bed_ids_reference(self):
        self._number_new_beds(self.bed_ids)
        if self.capacity and len(self.bed_ids) > self.capacity:
            return {'warning': {
                'title': _("Capacité dépassée"),
                'message': _(
                    "Cette chambre a une capacité de %(limit)s lit(s) et la liste en "
                    "contient %(count)s. Supprimez des lignes ou augmentez la "
                    "« Capacité », sinon l'enregistrement sera refusé.",
                    limit=self.capacity, count=len(self.bed_ids)),
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

    def _compute_operation_counts(self):
        Reservation = self.env['hotel.reservation']
        Housekeeping = self.env['hotel.housekeeping']
        Maintenance = self.env['hotel.maintenance.request']
        for room in self:
            room.reservation_count = Reservation.search_count(
                [('line_ids.room_id', '=', room.id)])
            room.housekeeping_count = Housekeeping.search_count(
                [('room_id', '=', room.id)])
            room.maintenance_count = Maintenance.search_count(
                [('room_id', '=', room.id)])

    def action_view_reservations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Réservations — %s") % self.name,
            'res_model': 'hotel.reservation',
            'view_mode': 'list,form',
            'domain': [('line_ids.room_id', '=', self.id)],
            'context': {'default_line_ids': [(0, 0, {'room_id': self.id})]},
        }

    def action_view_housekeeping(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Housekeeping — %s") % self.name,
            'res_model': 'hotel.housekeeping',
            'view_mode': 'list,form',
            'domain': [('room_id', '=', self.id)],
            'context': {'default_room_id': self.id},
        }

    def action_view_maintenance(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Travaux & Maintenance — %s") % self.name,
            'res_model': 'hotel.maintenance.request',
            'view_mode': 'list,form',
            'domain': [('room_id', '=', self.id)],
            'context': {'default_room_id': self.id},
        }

    @api.depends('technical_state')
    def _compute_maintenance(self):
        for room in self:
            room.maintenance = room.technical_state != 'in_service'

    def _compute_whole_room_price(self):
        RoomType = self.env['hotel.room.type']
        room_min = RoomType._hotel_min_price('room')
        bed_min = RoomType._hotel_min_price('bed')
        for room in self:
            room.room_price = room.whole_room_price = room_min
            room.bed_price = room.bed_price_min = bed_min

    def _get_whole_room_price(self, day):
        """Prix/nuit « à partir de » de la chambre entière (types de chambre)."""
        self.ensure_one()
        return self.room_price

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
            room.current_guest_ids = lines.mapped('partner_id')
            room.current_booking_type = current.booking_type if current else False
            # Par lit, une ligne par lit : montant = total des lits du séjour
            room.current_rental_amount = sum(lines.filtered(
                lambda l: l.reservation_id == current.reservation_id).mapped('price_unit'))                 if current else 0.0
            room.beds_free_count = len(beds) - len(taken)
            room.bed_availability = (
                "%s / %s lits libres" % (room.beds_free_count, len(beds))
                if beds else "")
            room.bed_map = room._render_bed_map(beds, taken)

            if room.maintenance:
                # Une demande de maintenance force maintenance=True sans toucher
                # à technical_state (qui peut rester 'in_service', absent de
                # `status`) : on retombe alors sur 'maintenance'.
                room.status = (room.technical_state
                               if room.technical_state != 'in_service'
                               else 'maintenance')
            elif not lines:
                # Le ménage est signalé mais ne bloque pas la vente
                room.status = ('cleaning' if room.housekeeping_status
                               not in ('clean', 'inspected') else 'available')
            elif whole or (beds and len(taken) >= len(beds)) or not beds:
                checked_in = lines.filtered(lambda l: l.state == 'checkin')
                room.status = 'occupied' if checked_in else 'reserved'
            else:
                room.status = 'partial'

    def _get_open_lines(self):
        """Lignes des réservations actives (confirmées ou enregistrées)."""
        return self.env['hotel.reservation.line'].search([
            ('room_id', 'in', self.ids),
            ('state', 'in', ('confirmed', 'checkin')),
        ])

    def _compute_reservation_totals(self):
        lines_by_room = {}
        for line in self.filtered('id')._get_open_lines():
            lines_by_room.setdefault(line.room_id.id, []).append(line)
        for room in self:
            lines = lines_by_room.get(room.id, [])
            total = paid = 0.0
            for line in lines:
                total += line.price_subtotal
                resa = line.reservation_id
                # Part de ce qui a été réellement encaissé, au prorata de la ligne
                if resa.amount_paid and resa.amount_total:
                    paid += (resa.amount_paid * line.price_subtotal
                             / resa.amount_total)
            room.current_reservation_total = total
            room.current_reservation_paid = paid
            room.current_reservation_due = total - paid
            room.current_reservation_paid_pct = (
                min(100.0, paid * 100.0 / total) if total else 0.0)
            room.current_reservation_count = len(
                {line.reservation_id.id for line in lines})

    def action_view_open_reservations(self):
        self.ensure_one()
        action = self.action_view_reservations()
        action['name'] = _("Réservations en cours — %s") % self.name
        action['domain'] = [('line_ids.room_id', '=', self.id),
                            ('state', 'in', ('confirmed', 'checkin'))]
        return action

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
                '<i class="oi" data-icon="bed"></i> %s</span>') % (
                    css, escape(label), escape(bed.name)))
        return Markup('<div class="o_hotel_bed_map">%s</div>') % Markup('').join(chips)

    def can_book_whole_room(self, checkin, checkout, ignore_reservation=False):
        """La chambre entière peut-elle être louée sur la période ?"""
        self.ensure_one()
        return self.is_available(checkin, checkout, ignore_reservation)

    def bookable_beds(self, checkin, checkout, ignore_reservation=False):
        """Lits louables individuellement sur la période."""
        self.ensure_one()
        return self.available_beds(checkin, checkout, ignore_reservation)

    # ------------------------------------------------------------------
    # Proposition des chambres / lits à la réservation (back-office et site)
    # ------------------------------------------------------------------
    @api.model
    def _hotel_whole_free_rooms(self, checkin, checkout, ignore_reservation=False,
                                domain=None):
        """Location « par chambre » : seules les chambres libres en entier
        (aucun lit loué, pas en maintenance) sur la période."""
        self = self.with_context(hotel_include_draft=True)
        rooms = self.search((domain or []) + [
            ('maintenance', '=', False)])
        if not (checkin and checkout and checkout > checkin):
            return rooms
        return rooms.filtered(
            lambda r: r.can_book_whole_room(checkin, checkout, ignore_reservation))

    @api.model
    def _hotel_bed_offer(self, checkin, checkout, ignore_reservation=False,
                         taken_beds=None, domain=None):
        """Location « par lit » : lits libres de chaque chambre, et chambres
        « partiellement réservées » (des lits pris, d'autres encore libres).
        `taken_beds` = lits déjà choisis dans la réservation en cours (ils
        comptent comme pris). Renvoie [(chambre, lits libres, partielle)]."""
        self = self.with_context(hotel_include_draft=True)
        taken_beds = taken_beds or self.env['hotel.bed']
        rooms = self.search((domain or []) + [
            ('maintenance', '=', False)])
        dated = checkin and checkout and checkout > checkin
        offer = []
        for room in rooms:
            beds = room.bed_ids.filtered('active')
            if not beds:
                continue
            free = (room.bookable_beds(checkin, checkout, ignore_reservation)
                    if dated else beds) - taken_beds
            if free:
                offer.append((room, free, free != beds))
        return offer

    @api.model
    def _hotel_proposed_beds(self, checkin, checkout, ignore_reservation=False,
                             taken_beds=None):
        """Lits proposés à la réservation au lit : d'abord ceux des chambres
        partiellement réservées ; s'il n'y en a aucune, ceux des chambres
        entièrement libres."""
        offer = self._hotel_bed_offer(checkin, checkout, ignore_reservation, taken_beds)
        partial = [free for room, free, is_partial in offer if is_partial]
        chosen = partial or [free for room, free, is_partial in offer]
        beds = self.env['hotel.bed']
        for free in chosen:
            beds |= free
        return beds

    @api.model
    def _hotel_ordered_free_rooms(self, checkin, checkout, ignore_reservation=False,
                                  guests=1, chosen=None, domain=None, capacity=0):
        """Location « par chambre » : chambres totalement vides (aucun lit
        loué, pas en maintenance) sur la période et l'étage (`domain`), avec
        N = personnes restant à loger (hors chambres déjà choisies) : celles
        dont la capacité = N, sinon N + 1, N + 2… (seul ce groupe est
        proposé). Si aucune ne peut loger tout le groupe : toutes, de la plus
        grande à la plus petite (groupe à répartir).
        `capacity` (capacité du type de chambre choisi, facultative) : seules
        les chambres vides de cette capacité sont proposées."""
        chosen = chosen or self.env['hotel.room']

        def size(room):
            return room.capacity or len(room.bed_ids.filtered('active'))
        remaining = max(guests - sum(size(r) for r in chosen), 1)
        rooms = self._hotel_whole_free_rooms(
            checkin, checkout, ignore_reservation, domain=domain) - chosen
        if capacity:
            return rooms.filtered(lambda r: size(r) == capacity).sorted(
                lambda r: r.name or '')
        fitting = [size(r) for r in rooms if size(r) >= remaining]
        if fitting:
            target = min(fitting)  # N + i, i le plus petit
            return rooms.filtered(lambda r: size(r) == target).sorted(
                lambda r: r.name or '')
        return rooms.sorted(lambda r: (-size(r), r.name or ''))

    @api.model
    def _hotel_ordered_free_beds(self, checkin, checkout, ignore_reservation=False,
                                 guests=1, taken_beds=None, domain=None, placement='together'):
        """Location « par lit », sur la période [checkin, checkout[ et l'étage
        (`domain`), avec N = nombre de personnes restant à loger. Chambres
        partielles = lits déjà loués par d'autres réservations, ou chambre
        entamée par la réservation en cours.
          - placement 'fill' (compléter les chambres, lits séparés) : d'abord
            les lits des chambres partielles ayant MOINS de N lits libres, en
            commençant par celles qui en ont le moins, jusqu'à loger tout le
            groupe ; si ces « trous » ne suffisent pas : règle 'together'.
          - placement 'together' (même chambre) : chambres partielles dont les
            lits libres = N + i, i = 0, 1, 2… (plus petite valeur trouvée).
        Les chambres totalement libres ne sont proposées que s'il n'existe
        aucune chambre partielle (lits = N + i). Seul le premier groupe
        trouvé est proposé. En dernier recours (rien ne loge le groupe) :
        tous les lits libres, chambres partielles d'abord.
        `taken_beds` = lits déjà choisis dans la réservation en cours : ils
        comptent comme placés."""
        taken_beds = taken_beds or self.env['hotel.bed']
        remaining = max(guests - len(taken_beds), 1)
        # Occupation réelle (autres réservations) : sans les lits en cours de choix
        offer = []
        for room, free, partial in self._hotel_bed_offer(
                checkin, checkout, ignore_reservation, domain=domain):
            left = free - taken_beds
            if left:
                started = bool(free & taken_beds)
                offer.append((room, left, partial or started, started))
        partials = [o for o in offer if o[2]]

        def key(o):
            return (not o[3], o[0].name or '')

        def beds_of(entries, ordered=False):
            beds = self.env['hotel.bed']
            for entry in (entries if ordered else sorted(entries, key=key)):
                beds += entry[1].sorted(lambda b: b.name or '')
            return beds

        if placement == 'fill':
            gaps = sorted([o for o in partials if len(o[1]) < remaining],
                          key=lambda o: (len(o[1]),) + key(o))
            chosen, count = [], 0
            for o in gaps:
                if count >= remaining:
                    break
                chosen.append(o)
                count += len(o[1])
            if count >= remaining:
                return beds_of(chosen, ordered=True)
        groups = [partials] if partials else [[o for o in offer if not o[2]]]
        for group in groups:
            fits = [o for o in group if len(o[1]) >= remaining]
            if fits:
                size = min(len(o[1]) for o in fits)  # N + i, i le plus petit
                return beds_of([o for o in fits if len(o[1]) == size])
        # Rien ne loge le groupe : tous les lits libres, partielles d'abord
        beds = self.env['hotel.bed']
        for o in sorted(offer, key=lambda o: (not o[2], -len(o[1])) + key(o)):
            beds += o[1].sorted(lambda b: b.name or '')
        return beds

    @api.model
    @api.readonly
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        ordered = hotel_proposal_name_search(self, name, domain, operator, limit)
        if ordered is not None:
            return ordered
        return super().name_search(name, domain, operator, limit)

    def _get_season(self, day, room_type=False):
        """Tarif saisonnier actif le jour donné : celui du type de chambre (de
        la réservation) en priorité, sinon un tarif global (sans type)."""
        self.ensure_one()
        Season = self.env['hotel.rate.season'].sudo()
        base = [('date_start', '<=', day), ('date_end', '>=', day),
                ('active', '=', True), ('company_id', 'in', (self.company_id.id, False))]
        season = Season.browse()
        if room_type:
            season = Season.search(base + [('room_type_id', '=', room_type.id)], limit=1)
        return season or Season.search(base + [('room_type_id', '=', False)], limit=1)

    def _get_night_price(self, day, booking_type='room', partner=False, room_type=False):
        """Prix d'UNE nuit : chambre entière, ou un seul lit (booking_type='bed').
        Priorité (cahier des charges §5) :
          1. tarif spécial du client,
          2. tarif spécial de la période (tarif saisonnier),
          3. prix du type de chambre choisi dans la réservation
             (à défaut : le type le moins cher)."""
        self.ensure_one()
        is_bed = booking_type == 'bed'
        if partner:
            special = (partner.hotel_special_bed_price if is_bed
                       else partner.hotel_special_room_price)
            if special:
                return special
        if day:
            season = self._get_season(day, room_type)
            season_price = season.bed_price if is_bed else season.price
            if season and season_price:
                return season_price
        if room_type:
            return room_type.bed_price if is_bed else room_type.room_price
        return self.bed_price if is_bed else self.room_price

    def _get_stay_unit_price(self, checkin, checkout, booking_type='room', partner=False,
                             room_type=False):
        """Prix moyen par nuit sur [checkin, checkout[ (les nuits d'un séjour à
        cheval sur deux périodes tarifaires sont prises chacune à leur prix)."""
        self.ensure_one()
        if not (checkin and checkout and checkout > checkin):
            return self._get_night_price(checkin, booking_type, partner, room_type)
        nights = (checkout - checkin).days
        total = sum(
            self._get_night_price(checkin + timedelta(days=n), booking_type, partner, room_type)
            for n in range(nights))
        return self.currency_id.round(total / nights) if self.currency_id else total / nights

    def _get_price_for_date(self, day):
        """Compatibilité : prix chambre entière d'une nuit."""
        return self._get_night_price(day, 'room')

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
            'whole_price': self.room_price,
            'beds': beds,
            'beds_ok': beds_ok,
            'bed_price_min': self.bed_price,
            'bookable': whole or beds_ok,
        }

    def _hotel_blocking_states(self):
        """États de réservation qui occupent une chambre / un lit. Pour les
        propositions (contexte `hotel_include_draft`), une réservation en
        brouillon compte aussi : ce qui est déjà pris n'est plus proposé."""
        if self.env.context.get('hotel_include_draft'):
            return ('draft', 'confirmed', 'checkin')
        return ('confirmed', 'checkin')

    def is_available(self, checkin, checkout, ignore_reservation=False):
        """Renvoie True si la chambre est libre sur la période [checkin, checkout[."""
        self.ensure_one()
        if self.maintenance:
            return False
        domain = [
            ('room_id', '=', self.id),
            ('state', 'in', self._hotel_blocking_states()),
            ('checkin', '<', checkout),
            ('checkout', '>', checkin),
        ]
        if ignore_reservation:
            domain.append(('reservation_id', '!=', ignore_reservation.id))
        return not self.env['hotel.reservation.line'].search_count(domain)
