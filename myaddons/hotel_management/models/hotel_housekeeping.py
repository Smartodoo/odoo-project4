from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HotelHousekeeping(models.Model):
    _name = 'hotel.housekeeping'
    _description = "Tâche de ménage"
    _order = 'scheduled_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=lambda self: _('Nouveau'))
    room_id = fields.Many2one('hotel.room', string="Chambre", required=True, tracking=True)
    staff_id = fields.Many2one('hotel.staff', string="Agent d'entretien", tracking=True)
    reservation_id = fields.Many2one('hotel.reservation', string="Séjour lié")
    maintenance_id = fields.Many2one(
        'hotel.maintenance.request', string="Demande de réparation", readonly=True,
        copy=False)
    cleaning_type = fields.Selection([
        ('checkout', 'Après départ'),
        ('daily', 'Quotidien'),
        ('deep', 'Grand ménage'),
        ('other', 'Autre'),
    ], string="Type", default='daily', required=True)
    scheduled_date = fields.Date(
        string="Date prévue", default=fields.Date.context_today)
    # Cycle du cahier des charges §14
    state = fields.Selection([
        ('todo', 'À nettoyer'),
        ('inprogress', 'En nettoyage'),
        ('done', 'Nettoyée'),
        ('inspected', 'Contrôlée'),
        ('to_repair', 'À réparer'),
        ('cancel', 'Annulé'),
    ], string="État", default='todo', tracking=True)
    inspected_by_id = fields.Many2one(
        'res.users', string="Contrôlée par", readonly=True, copy=False)
    note = fields.Text(string="Notes")
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hotel.housekeeping') or _('Nouveau')
        records = super().create(vals_list)
        records._notify_assignment()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get('staff_id'):
            self._notify_assignment()
        return res

    def _notify_assignment(self):
        """Alerte « Chambre nécessitant un nettoyage » (cahier des charges §18) :
        activité pour l'agent affecté (s'il a un compte utilisateur)."""
        for rec in self.filtered(lambda r: r.state == 'todo' and r.staff_id.user_id):
            summary = _("Nettoyer la chambre %s", rec.room_id.name)
            if rec.activity_ids.filtered(lambda a: a.summary == summary):
                continue
            rec.sudo().activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=rec.scheduled_date or fields.Date.context_today(rec),
                summary=summary,
                user_id=rec.staff_id.user_id.id)

    def action_start(self):
        for rec in self:
            rec.state = 'inprogress'
            if rec.room_id:
                rec.room_id.housekeeping_status = 'inprogress'

    def action_done(self):
        for rec in self:
            rec.state = 'done'
            if rec.room_id:
                rec.room_id.housekeeping_status = 'clean'
            rec.activity_ids.action_feedback(feedback=_("Ménage terminé"))

    def action_inspect(self):
        """Contrôle par le responsable : la chambre est validée « Contrôlée »."""
        if not self.env.user.has_group('hotel_management.group_hotel_manager'):
            raise UserError(_("Seul un responsable peut contrôler une chambre."))
        for rec in self:
            if rec.state != 'done':
                raise UserError(_("Seule une chambre nettoyée peut être contrôlée."))
            rec.write({'state': 'inspected', 'inspected_by_id': self.env.user.id})
            if rec.room_id:
                rec.room_id.housekeeping_status = 'inspected'

    def action_to_repair(self):
        """Problème constaté pendant le ménage : la chambre passe « À réparer »
        et une demande de travaux est créée."""
        self.ensure_one()
        request = self.env['hotel.maintenance.request'].create({
            'name': _("Réparation signalée au ménage — chambre %s", self.room_id.name),
            'room_id': self.room_id.id,
            'description': self.note or False,
        })
        self.write({'state': 'to_repair', 'maintenance_id': request.id})
        if self.room_id:
            self.room_id.housekeeping_status = 'to_repair'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hotel.maintenance.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_reset(self):
        self.write({'state': 'todo'})
        for rec in self.filtered('room_id'):
            rec.room_id.housekeeping_status = 'dirty'
