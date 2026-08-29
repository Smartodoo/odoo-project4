from odoo import fields, models


class HotelStaff(models.Model):
    _name = 'hotel.staff'
    _description = "Personnel hôtelier"
    _order = 'name'
    _inherit = ['mail.thread']

    name = fields.Char(string="Nom", required=True, tracking=True)
    role = fields.Selection([
        ('reception', 'Réception'),
        ('housekeeping', 'Ménage'),
        ('maintenance', 'Maintenance / Technicien'),
        ('restaurant', 'Restauration'),
        ('manager', 'Encadrement'),
        ('other', 'Autre'),
    ], string="Fonction", default='other', required=True, tracking=True)
    phone = fields.Char(string="Téléphone")
    email = fields.Char(string="E-mail")
    user_id = fields.Many2one('res.users', string="Utilisateur lié")
    image = fields.Image(string="Photo")
    note = fields.Text(string="Notes")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)
