from odoo import api, fields, models, _


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
    cleaning_type = fields.Selection([
        ('checkout', 'Après départ'),
        ('daily', 'Quotidien'),
        ('deep', 'Grand ménage'),
        ('other', 'Autre'),
    ], string="Type", default='daily', required=True)
    scheduled_date = fields.Date(
        string="Date prévue", default=fields.Date.context_today)
    state = fields.Selection([
        ('todo', 'À faire'),
        ('inprogress', 'En cours'),
        ('done', 'Terminé'),
        ('cancel', 'Annulé'),
    ], string="État", default='todo', tracking=True)
    note = fields.Text(string="Notes")
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hotel.housekeeping') or _('Nouveau')
        return super().create(vals_list)

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

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_reset(self):
        self.write({'state': 'todo'})
