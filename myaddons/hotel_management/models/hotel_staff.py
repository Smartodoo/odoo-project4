from odoo import api, fields, models


class HotelStaff(models.Model):
    """Agent de l'auberge (réception, ménage, maintenance). Relié à la fiche
    Employé d'Odoo (contrat, service, planning, présences, congés : cahier des
    charges §13)."""
    _name = 'hotel.staff'
    _description = "Personnel hôtelier"
    _order = 'name'
    _inherit = ['mail.thread']

    name = fields.Char(string="Nom", required=True, tracking=True)
    employee_id = fields.Many2one(
        'hr.employee', string="Fiche employé", tracking=True,
        help="Employé Odoo : contrat, service, horaires, présences et congés.")
    role = fields.Selection([
        ('reception', 'Réception'),
        ('housekeeping', 'Ménage'),
        ('maintenance', 'Maintenance / Technicien'),
        ('manager', 'Encadrement'),
        ('other', 'Autre'),
    ], string="Fonction", default='other', required=True, tracking=True)
    department_id = fields.Many2one(
        related='employee_id.department_id', string="Service")
    job_title = fields.Char(related='employee_id.job_title', string="Poste")
    resource_calendar_id = fields.Many2one(
        related='employee_id.resource_calendar_id', string="Planning (horaires)")
    phone = fields.Char(string="Téléphone")
    email = fields.Char(string="E-mail")
    user_id = fields.Many2one('res.users', string="Utilisateur lié")
    image = fields.Image(string="Photo")
    note = fields.Text(string="Notes")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        emp = self.employee_id
        if emp:
            self.name = emp.name
            self.phone = emp.mobile_phone or emp.work_phone or self.phone
            self.email = emp.work_email or self.email
            self.user_id = emp.user_id or self.user_id

    def action_create_employee(self):
        """Crée la fiche employé Odoo à partir de l'agent."""
        for rec in self.filtered(lambda s: not s.employee_id):
            rec.employee_id = self.env['hr.employee'].create({
                'name': rec.name,
                'mobile_phone': rec.phone,
                'work_email': rec.email,
                'user_id': rec.user_id.id or False,
                'company_id': rec.company_id.id,
            })

    def action_open_employee(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'res_id': self.employee_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
