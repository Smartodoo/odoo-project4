from odoo import api, fields, models, _


class HotelRestaurantCategory(models.Model):
    _name = 'hotel.restaurant.category'
    _description = "Catégorie de restauration"
    _order = 'sequence, name'

    name = fields.Char(string="Catégorie", required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    item_ids = fields.One2many('hotel.restaurant.item', 'category_id', string="Articles")


class HotelRestaurantItem(models.Model):
    _name = 'hotel.restaurant.item'
    _description = "Article de restauration"
    _order = 'category_id, name'

    name = fields.Char(string="Article", required=True, translate=True)
    code = fields.Char(string="Code")
    category_id = fields.Many2one('hotel.restaurant.category', string="Catégorie")
    price = fields.Monetary(string="Prix", currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    available = fields.Boolean(string="Disponible", default=True)
    description = fields.Text(string="Description")
    image = fields.Image(string="Photo")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)


class HotelRestaurantOrder(models.Model):
    _name = 'hotel.restaurant.order'
    _description = "Commande de restauration"
    _order = 'order_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=lambda self: _('Nouveau'))
    partner_id = fields.Many2one('res.partner', string="Client", tracking=True)
    reservation_id = fields.Many2one(
        'hotel.reservation', string="Séjour / Réservation", tracking=True)
    room_id = fields.Many2one('hotel.room', string="Chambre")
    order_date = fields.Datetime(
        string="Date", default=fields.Datetime.now, required=True)
    charge_to_room = fields.Boolean(
        string="Facturer sur le séjour", default=False,
        help="Si coché, le montant est ajouté au total du séjour lié.")
    line_ids = fields.One2many(
        'hotel.restaurant.order.line', 'order_id', string="Articles", copy=True)
    amount_total = fields.Monetary(
        string="Total", compute='_compute_amount_total', store=True, tracking=True)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('confirmed', 'Confirmée'),
        ('served', 'Servie'),
        ('invoiced', 'Facturée'),
        ('cancel', 'Annulée'),
    ], string="État", default='draft', tracking=True, copy=False)
    note = fields.Text(string="Notes")

    @api.depends('line_ids.price_subtotal')
    def _compute_amount_total(self):
        for order in self:
            order.amount_total = sum(order.line_ids.mapped('price_subtotal'))

    @api.onchange('reservation_id')
    def _onchange_reservation_id(self):
        if self.reservation_id:
            self.partner_id = self.reservation_id.partner_id
            rooms = self.reservation_id.line_ids.mapped('room_id')
            self.room_id = rooms[:1].id if rooms else False
            self.charge_to_room = True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hotel.restaurant.order') or _('Nouveau')
        return super().create(vals_list)

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_serve(self):
        self.write({'state': 'served'})

    def action_invoice(self):
        self.write({'state': 'invoiced'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})


class HotelRestaurantOrderLine(models.Model):
    _name = 'hotel.restaurant.order.line'
    _description = "Ligne de commande restauration"

    order_id = fields.Many2one(
        'hotel.restaurant.order', string="Commande", required=True, ondelete='cascade')
    item_id = fields.Many2one(
        'hotel.restaurant.item', string="Article", required=True)
    name = fields.Char(string="Désignation")
    qty = fields.Float(string="Quantité", default=1.0)
    price_unit = fields.Monetary(string="Prix unitaire", currency_field='currency_id')
    price_subtotal = fields.Monetary(
        string="Sous-total", compute='_compute_subtotal', store=True)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True)

    @api.depends('qty', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.qty * line.price_unit

    @api.onchange('item_id')
    def _onchange_item_id(self):
        if self.item_id:
            self.price_unit = self.item_id.price
            self.name = self.item_id.name
