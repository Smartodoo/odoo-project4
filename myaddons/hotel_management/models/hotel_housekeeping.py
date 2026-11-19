from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class HotelHousekeeping(models.Model):
    _name = 'hotel.housekeeping'
    _description = "Tâche de ménage"
    _order = 'scheduled_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=lambda self: _('Nouveau'))
    room_id = fields.Many2one('hotel.room', string="Chambre", required=True, tracking=True)
    # Ménage de la chambre entière ou seulement de certains lits (dortoir)
    target = fields.Selection([
        ('room', 'Chambre entière'),
        ('bed', 'Lits'),
    ], string="Ménage de", default='room', required=True, tracking=True)
    bed_ids = fields.Many2many(
        'hotel.bed', 'hotel_housekeeping_bed_rel', 'housekeeping_id', 'bed_id',
        string="Lits", domain="[('room_id', '=', room_id)]")
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

    @api.constrains('target', 'bed_ids', 'room_id')
    def _check_beds(self):
        for rec in self:
            if rec.target != 'bed':
                continue
            if not rec.bed_ids:
                raise ValidationError(_(
                    "Ménage des lits (%s) : choisissez au moins un lit.", rec.name))
            if rec.bed_ids.room_id != rec.room_id:
                raise ValidationError(_(
                    "Les lits à nettoyer doivent appartenir à la chambre %s.",
                    rec.room_id.name))

    @api.onchange('room_id')
    def _onchange_room_id_beds(self):
        self.bed_ids = self.bed_ids.filtered(lambda b: b.room_id == self.room_id)

    @api.onchange('target')
    def _onchange_target(self):
        if self.target == 'room':
            self.bed_ids = False

    @api.depends('name', 'room_id', 'target', 'bed_ids')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s — %s" % (rec.name or '', rec._target_label())

    def _target_label(self):
        """« Chambre 101 » ou « Lits L1, L2 (chambre 101) »."""
        self.ensure_one()
        if self.target == 'bed' and self.bed_ids:
            return _("Lits %(beds)s (chambre %(room)s)",
                     beds=", ".join(self.bed_ids.mapped('name')),
                     room=self.room_id.name or '')
        return _("Chambre %s", self.room_id.name or '')

    def _set_housekeeping_status(self, status):
        """Répercute l'état du ménage : sur la chambre et tous ses lits pour un
        ménage « chambre entière », sur les lits concernés seulement sinon.
        sudo : l'équipe de ménage n'a que la lecture sur les lits."""
        for rec in self.filtered('room_id'):
            if rec.target == 'bed':
                rec.bed_ids.sudo().write({'housekeeping_status': status})
            else:
                rec.room_id.housekeeping_status = status
                rec.room_id.bed_ids.sudo().write({'housekeeping_status': status})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hotel.housekeeping') or _('Nouveau')
        records = super().create(vals_list)
        # Un ménage de lits à faire signale tout de suite ces lits « À nettoyer »
        records.filtered(
            lambda r: r.target == 'bed' and r.state == 'todo'
        )._set_housekeeping_status('dirty')
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
            summary = _("Nettoyer : %s", rec._target_label())
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
            rec._set_housekeeping_status('inprogress')

    def action_done(self):
        for rec in self:
            rec.state = 'done'
            rec._set_housekeeping_status('clean')
            rec.activity_ids.action_feedback(feedback=_("Ménage terminé"))

    def action_inspect(self):
        """Contrôle par le responsable : la chambre est validée « Contrôlée »."""
        if not self.env.user.has_group('hotel_management.group_hotel_manager'):
            raise UserError(_("Seul un responsable peut contrôler une chambre."))
        for rec in self:
            if rec.state != 'done':
                raise UserError(_("Seule une chambre nettoyée peut être contrôlée."))
            rec.write({'state': 'inspected', 'inspected_by_id': self.env.user.id})
            rec._set_housekeeping_status('inspected')

    def action_to_repair(self):
        """Problème constaté pendant le ménage : la chambre passe « À réparer »
        et une demande de travaux est créée."""
        self.ensure_one()
        request = self.env['hotel.maintenance.request'].create({
            'name': _("Réparation signalée au ménage — %s", self._target_label()),
            'room_id': self.room_id.id,
            'description': self.note or False,
        })
        self.write({'state': 'to_repair', 'maintenance_id': request.id})
        self._set_housekeeping_status('to_repair')
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
        self._set_housekeeping_status('dirty')
