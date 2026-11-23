import re
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Fonction de l'agent -> groupes de l'utilisateur lié (xmlid)
ROLE_GROUPS = {
    'reception': ['hotel_management.group_hotel_user'],
    'housekeeping': ['hotel_management.group_hotel_housekeeping'],
    'maintenance': ['hotel_management.group_hotel_housekeeping'],
    'manager': ['hotel_management.group_hotel_manager'],
    'other': [],
}
HOTEL_GROUPS = ['hotel_management.group_hotel_user',
                'hotel_management.group_hotel_housekeeping',
                'hotel_management.group_hotel_manager']


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
        ('housekeeping', 'Housekeeping'),
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

    login = fields.Char(related='user_id.login', string="Identifiant de connexion")

    # ------------------------------------------------------------------
    # Agent = employé + utilisateur
    # ------------------------------------------------------------------
    def _check_can_manage_users(self):
        if not (self.env.su or self.env.user.has_group('hotel_management.group_hotel_manager')
                or self.env.user.has_group('base.group_erp_manager')):
            raise UserError(_(
                "Seul un responsable de l'auberge peut créer ou modifier un agent "
                "(un utilisateur Odoo est créé pour chaque agent)."))

    @api.model
    def _role_groups(self, role):
        groups = self.env['res.groups']
        for xmlid in ROLE_GROUPS.get(role or 'other', []):
            groups |= self.env.ref(xmlid)
        return groups

    def _make_login(self):
        """Identifiant : l'e-mail s'il est saisi, sinon « prenom.nom » (sans
        accents), rendu unique par un numéro."""
        self.ensure_one()
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        if self.email and not Users.search_count([('login', '=ilike', self.email.strip())]):
            return self.email.strip().lower()
        base = unicodedata.normalize('NFKD', self.name or 'agent').encode('ascii', 'ignore').decode()
        base = re.sub(r'[^a-z0-9]+', '.', base.lower()).strip('.') or 'agent'
        login, n = base, 1
        while Users.search_count([('login', '=', login)]):
            n += 1
            login = '%s%s' % (base, n)
        return login

    def _ensure_user_and_employee(self):
        """Crée ce qui manque : utilisateur (droits selon la fonction) et
        fiche employé reliée à cet utilisateur."""
        Users = self.env['res.users'].sudo()
        Employee = self.env['hr.employee'].sudo()
        for rec in self:
            user = rec.user_id or rec.employee_id.user_id
            if not user:
                user = Users.with_context(no_reset_password=not rec.email).create({
                    'name': rec.name,
                    'login': rec._make_login(),
                    'email': rec.email or False,
                    'phone': rec.phone or False,
                    'company_id': rec.company_id.id,
                    'company_ids': [(6, 0, rec.company_id.ids)],
                    'group_ids': [(6, 0, (self.env.ref('base.group_user')
                                          | rec._role_groups(rec.role)).ids)],
                })
            else:
                rec._apply_role_groups(user)
            employee = rec.employee_id or Employee.search(
                [('user_id', '=', user.id), ('company_id', '=', rec.company_id.id)], limit=1)
            if not employee:
                employee = Employee.create({
                    'name': rec.name,
                    'mobile_phone': rec.phone or False,
                    'work_email': rec.email or False,
                    'user_id': user.id,
                    'company_id': rec.company_id.id,
                    'image_1920': rec.image or False,
                })
            elif not employee.user_id:
                employee.user_id = user
            vals = {}
            if rec.user_id != user:
                vals['user_id'] = user.id
            if rec.employee_id != employee:
                vals['employee_id'] = employee.id
            if vals:
                super(HotelStaff, rec).write(vals)

    def _apply_role_groups(self, user):
        """Remplace les groupes Auberge de l'utilisateur par ceux de la fonction."""
        self.ensure_one()
        hotel = self.env['res.groups']
        for xmlid in HOTEL_GROUPS:
            hotel |= self.env.ref(xmlid)
        wanted = self._role_groups(self.role)
        commands = [(3, g.id) for g in hotel - wanted] + [(4, g.id) for g in wanted]
        user.sudo().write({'group_ids': commands})

    @api.model_create_multi
    def create(self, vals_list):
        self._check_can_manage_users()
        records = super().create(vals_list)
        records._ensure_user_and_employee()
        return records

    def write(self, vals):
        if {'role', 'active', 'user_id', 'employee_id'} & set(vals):
            self._check_can_manage_users()
        res = super().write(vals)
        for rec in self:
            emp_vals, user_vals = {}, {}
            if 'name' in vals:
                emp_vals['name'] = user_vals['name'] = rec.name
            if 'phone' in vals:
                emp_vals['mobile_phone'] = rec.phone or False
                user_vals['phone'] = rec.phone or False
            if 'email' in vals:
                emp_vals['work_email'] = rec.email or False
                user_vals['email'] = rec.email or False
            if 'active' in vals:
                emp_vals['active'] = user_vals['active'] = rec.active
            if rec.employee_id and emp_vals:
                rec.employee_id.sudo().write(emp_vals)
            if rec.user_id and user_vals:
                rec.user_id.sudo().write(user_vals)
            if 'role' in vals and rec.user_id:
                rec._apply_role_groups(rec.user_id)
        return res

    def action_create_employee(self):
        """Agents existants : crée la fiche employé et l'utilisateur manquants."""
        self._check_can_manage_users()
        self._ensure_user_and_employee()

    def action_open_user(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.users',
            'res_id': self.user_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_employee(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'res_id': self.employee_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
