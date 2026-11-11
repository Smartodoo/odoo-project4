from odoo import api, fields, models, _


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
        requests._notify_new_request()
        return requests

    def _notify_new_request(self):
        """Alerte « Chambre en maintenance » (cahier des charges §18) :
        responsables notifiés, activité pour le technicien affecté."""
        group = self.env.ref('hotel_management.group_hotel_manager',
                             raise_if_not_found=False)
        partners = group.sudo().all_user_ids.filtered('active').partner_id             if group else self.env['res.partner']
        for rec in self:
            room = rec.room_id.name or '-'
            rec.sudo().message_post(
                body=_("Nouvelle demande de travaux : %(name)s (chambre %(room)s).",
                       name=rec.name, room=room),
                partner_ids=partners.ids, subtype_xmlid='mail.mt_note')
            if rec.staff_id.user_id:
                rec.sudo().activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=_("Intervention chambre %s", room),
                    note=rec.description or rec.name,
                    user_id=rec.staff_id.user_id.id)

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
            # Après réparation, la chambre doit être nettoyée avant d'être revendue
            if rec.room_id.housekeeping_status == 'to_repair':
                rec.room_id.housekeeping_status = 'dirty'

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
