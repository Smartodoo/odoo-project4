from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HotelRateSeason(models.Model):
    _name = 'hotel.rate.season'
    _description = "Tarif saisonnier"
    _order = 'date_start desc, id desc'

    name = fields.Char(string="Saison", required=True)
    date_start = fields.Date(string="Du", required=True)
    date_end = fields.Date(string="Au", required=True)
    room_type_id = fields.Many2one(
        'hotel.room.type', string="Type de chambre",
        help="Laisser vide pour appliquer à tous les types de chambres.")
    price = fields.Monetary(string="Prix / nuit", required=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError(
                    _("La date de fin doit être postérieure ou égale à la date de début."))
