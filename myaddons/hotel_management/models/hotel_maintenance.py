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
        """Aligne l'état technique de la chambre sur ses travaux : au moins une
        demande ouverte -> « Maintenance » ; plus aucune -> « En service ».
        On ne touche pas à « Hors service » (fermeture décidée à la main)."""
        if not room:
            return
        open_count = self.search_count([
            ('room_id', '=', room.id),
            ('state', 'in', ('new', 'inprogress')),
        ])
        if open_count:
            if room.technical_state == 'in_service':
                room.technical_state = 'maintenance'
        elif room.technical_state == 'maintenance':
            room.technical_state = 'in_service'

    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create(vals_list)
        for rec in requests:
            rec._sync_room_maintenance(rec.room_id)
        return requests

    def write(self, vals):
        rooms = self.mapped('room_id')
        res = super().write(vals)
        if 'room_id' in vals or 'state' in vals:
            rooms |= self.mapped('room_id')
            for room in rooms:
                self._sync_room_maintenance(room)
        return res

    def action_start(self):
        for rec in self:
            rec.state = 'inprogress'
            rec._sync_room_maintenance(rec.room_id)

    def action_done(self):
        for rec in self:
            rec.state = 'done'
            rec.done_date = fields.Date.context_today(rec)
            rec._sync_room_maintenance(rec.room_id)

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancel'
            rec._sync_room_maintenance(rec.room_id)

    def action_set_out_of_service(self):
        """Après la fin des travaux : fermer durablement la chambre
        (statut « Hors service ») au lieu de la remettre disponible."""
        for rec in self:
            if rec.room_id:
                rec.room_id.technical_state = 'out_of_service'

    def action_reset(self):
        for rec in self:
            rec.state = 'new'
            rec._sync_room_maintenance(rec.room_id)
