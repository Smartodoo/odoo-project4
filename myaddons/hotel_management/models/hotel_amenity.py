from odoo import fields, models


class HotelAmenity(models.Model):
    _name = 'hotel.amenity'
    _description = "Équipement / Caractéristique de chambre"
    _order = 'sequence, name'

    name = fields.Char(string="Nom", required=True, translate=True)
    sequence = fields.Integer(default=10)
    icon = fields.Char(string="Icône", help="Classe Font Awesome, ex : fa-wifi, fa-tv, fa-snowflake")
    active = fields.Boolean(default=True)
