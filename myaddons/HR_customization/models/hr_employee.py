from odoo import models, fields, api

class HrEmployeeExt(models.Model):
    _inherit = 'hr.employee'

    is_commercial = fields.Boolean(string="Est un commercial", help="Employé responsable de la vente")

