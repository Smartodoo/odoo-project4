from odoo import api, fields, models


class HotelRoomType(models.Model):
    _name = 'hotel.room.type'
    _description = "Type de chambre"
    _order = 'sequence, name'

    name = fields.Char(string="Type", required=True, translate=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(string="Code")
    list_price = fields.Monetary(string="Prix / nuit", currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    default_capacity = fields.Integer(string="Capacité (personnes)", default=2)
    rental_mode = fields.Selection([
        ('room', 'Chambre entière'),
        ('bed', 'Au lit (dortoir)'),
    ], string="Mode de location", default='room', required=True,
        help="Mode appliqué par défaut aux chambres de ce type.")
    amenity_ids = fields.Many2many('hotel.amenity', string="Équipements")
    description = fields.Text(string="Description")
    image = fields.Image(string="Photo")
    active = fields.Boolean(default=True)
    room_ids = fields.One2many('hotel.room', 'room_type_id', string="Chambres")
    room_count = fields.Integer(string="Nb chambres", compute='_compute_room_count')

    def _compute_room_count(self):
        groups = self.env['hotel.room'].read_group(
            [('room_type_id', 'in', self.ids)], ['room_type_id'], ['room_type_id'])
        mapping = {g['room_type_id'][0]: g['room_type_id_count'] for g in groups}
        for rec in self:
            rec.room_count = mapping.get(rec.id, 0)

    def action_view_rooms(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'hotel.room',
            'view_mode': 'kanban,tree,form',
            'domain': [('room_type_id', '=', self.id)],
            'context': {'default_room_type_id': self.id},
        }

    def _website_cards(self, rooms):
        """Données des cartes « types de chambre » de la page d'accueil.

        Seuls les types ayant au moins une chambre de `rooms` (chambres publiées)
        sont retournés ; prix, capacité et équipements sont calculés sur ces chambres.
        """
        # Mêmes équipements que la section Confort (« Afficher sur l'accueil »)
        amenities = self.env['hotel.amenity'].search([('website_home', '=', True)])
        cards = []
        for rtype in self:
            type_rooms = rooms.filtered(lambda room: room.room_type_id == rtype)
            if not type_rooms:
                continue
            prices = [room.bed_price_min if room.rental_mode == 'bed' else room.whole_room_price
                      for room in type_rooms]
            prices = [price for price in prices if price]
            room_with_image = type_rooms.filtered('image')[:1]
            if rtype.with_context(bin_size=True).image:
                image_url = '/web/image/hotel.room.type/%s/image' % rtype.id
            elif room_with_image:
                image_url = '/web/image/hotel.room/%s/image' % room_with_image.id
            else:
                image_url = False
            cards.append({
                'type': rtype,
                'image_url': image_url,
                'price': min(prices) if prices else 0.0,
                'capacity': max(type_rooms.mapped('capacity') or [rtype.default_capacity]),
                'amenities': amenities._website_common_to(type_rooms)[:5],
            })
        return cards
