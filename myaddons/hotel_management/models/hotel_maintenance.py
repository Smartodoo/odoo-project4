from odoo import api, fields, models


class HotelMaintenanceRequest(models.Model):
    _name = 'hotel.maintenance.request'
    _description = "Demande de travaux / maintenance"
    _order = 'request_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Objet", required=True, tracking=True)
    room_id = fields.Many2one('hotel.room', string="Chambre", tracking=True)
    staff_id = fields.Many2one('hotel.staff', string="Technicien", tracking=True)
    category = fields.Selection([
        ('plumbing', 'Plomberie'),
        ('electrical', 'Électricité'),
        ('furniture', 'Mobilier'),
        ('hvac', 'Climatisation / Chauffage'),
        ('other', 'Autre'),
    ], string="Catégorie", default='other')
    priority = fields.Selection([
        ('0', 'Basse'),
        ('1', 'Normale'),
        ('2', 'Haute'),
        ('3', 'Urgente'),
    ], string="Priorité", default='1')
    description = fields.Text(string="Description")
    request_date = fields.Date(
        string="Date demande", default=fields.Date.context_today)
    done_date = fields.Date(string="Date résolution", readonly=True)
    cost = fields.Monetary(string="Coût", currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    state = fields.Selection([
        ('new', 'Nouvelle'),
        ('inprogress', 'En cours'),
        ('done', 'Terminée'),
        ('cancel', 'Annulée'),
    ], string="État", default='new', tracking=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    def _sync_room_maintenance(self, room):
        """La chambre est en maintenance s'il reste au moins une demande ouverte."""
        if not room:
            return
        open_count = self.search_count([
            ('room_id', '=', room.id),
            ('state', 'in', ('new', 'inprogress')),
        ])
        room.maintenance = bool(open_count)

    def action_start(self):
        for rec in self:
            rec.state = 'inprogress'
            if rec.room_id:
                rec.room_id.maintenance = True

    def action_done(self):
        for rec in self:
            rec.state = 'done'
            rec.done_date = fields.Date.context_today(rec)
            rec._sync_room_maintenance(rec.room_id)

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancel'
            rec._sync_room_maintenance(rec.room_id)

    def action_reset(self):
        for rec in self:
            rec.state = 'new'
            if rec.room_id:
                rec.room_id.maintenance = True
