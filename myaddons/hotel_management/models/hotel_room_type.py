from odoo import _, api, fields, models


class HotelRoomType(models.Model):
    _name = 'hotel.room.type'
    _description = "Type de chambre"
    _order = 'sequence, name'

    name = fields.Char(string="Type", required=True, translate=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(string="Code")
    # Prix de base (cf. réservation : le type de chambre choisi fixe le prix)
    room_price = fields.Monetary(
        string="Prix chambre / nuit", currency_field='currency_id',
        help="Prix d'une nuit pour une chambre entière réservée avec ce type.")
    bed_price = fields.Monetary(
        string="Prix lit / nuit", currency_field='currency_id',
        help="Prix d'une nuit pour UN lit réservé avec ce type (location au lit).")
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    capacity = fields.Integer(
        string="Capacité (personnes)",
        help="Facultatif. Réservation par chambre avec ce type : seules les "
             "chambres de cette capacité sont proposées. Vide : chambres de "
             "capacité = nombre de personnes, sinon + 1, + 2…")
    amenity_ids = fields.Many2many('hotel.amenity', string="Équipements")
    description = fields.Text(string="Description")
    image = fields.Image(string="Photo")
    active = fields.Boolean(default=True)
    reservation_count = fields.Integer(
        string="Nb réservations", compute='_compute_reservation_count')

    _capacity_non_negative = models.Constraint(
        'CHECK(capacity IS NULL OR capacity >= 0)',
        "La capacit\u00e9 d'un type de chambre ne peut pas \u00eatre n\u00e9gative.",
    )
    _prices_non_negative = models.Constraint(
        'CHECK(room_price >= 0 AND bed_price >= 0)',
        "Les prix d'un type de chambre ne peuvent pas \u00eatre n\u00e9gatifs.",
    )

    @api.model
    def _hotel_cheapest(self, booking_type):
        """Type actif le moins cher ayant un prix pour ce mode de location
        ('room' : prix chambre, 'bed' : prix lit)."""
        fname = 'bed_price' if booking_type == 'bed' else 'room_price'
        types = self.search([(fname, '>', 0)])
        return types.sorted(lambda t: (t[fname], t.sequence, t.id))[:1]

    @api.model
    def _hotel_min_price(self, booking_type):
        return self._hotel_cheapest(booking_type)[
            'bed_price' if booking_type == 'bed' else 'room_price'] or 0.0

    def _compute_reservation_count(self):
        groups = self.env['hotel.reservation']._read_group(
            [('room_type_id', 'in', self.ids)], ['room_type_id'], ['__count'])
        mapping = {room_type.id: count for room_type, count in groups}
        for rec in self:
            rec.reservation_count = mapping.get(rec.id, 0)

    def action_view_reservations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'hotel.reservation',
            'view_mode': 'list,form',
            'domain': [('room_type_id', '=', self.id)],
            'context': {'default_room_type_id': self.id},
        }

    def _website_cards(self, rooms):
        """Données des cartes « types de chambre » de la page d'accueil : les
        types ayant un prix ; capacité = plus grande chambre publiée."""
        amenities = self.env['hotel.amenity'].search([('website_home', '=', True)])
        room_with_image = rooms.filtered('image')[:1]
        capacity = max(rooms.mapped('capacity') or [0])
        cards = []
        for rtype in self.filtered(lambda t: t.room_price or t.bed_price):
            if rtype.with_context(bin_size=True).image:
                image_url = '/web/image/hotel.room.type/%s/image' % rtype.id
            elif room_with_image:
                image_url = '/web/image/hotel.room/%s/image' % room_with_image.id
            else:
                image_url = False
            cards.append({
                'type': rtype,
                'image_url': image_url,
                'price': rtype.room_price or rtype.bed_price,
                'per_bed': not rtype.room_price,
                'capacity': capacity,
                'amenities': (rtype.amenity_ids & amenities or amenities._website_common_to(rooms))[:5],
            })
        return cards
