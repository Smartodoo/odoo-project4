from odoo import fields, models


class HotelAmenity(models.Model):
    _name = 'hotel.amenity'
    _description = "Équipement / Caractéristique de chambre"
    _order = 'sequence, name'

    name = fields.Char(string="Nom", required=True, translate=True)
    sequence = fields.Integer(default=10)
    icon = fields.Char(string="Icône", help="Classe Font Awesome, ex : fa-wifi, fa-tv, fa-snowflake")
    active = fields.Boolean(default=True)
    website_home = fields.Boolean(
        string="Afficher sur l'accueil", default=True,
        help="Affiche cet équipement dans la section « Confort » de la page d'accueil du site.")

    # Utilisés par la page d'accueil du site (QWeb n'accepte pas les lambdas à fermeture)
    def _website_room_count(self, rooms):
        """Nombre de chambres de `rooms` qui ont cet équipement."""
        self.ensure_one()
        return len(rooms.filtered(lambda room: self in room.amenity_ids))

    def _website_common_to(self, rooms):
        """Équipements présents dans toutes les chambres de `rooms`."""
        if not rooms:
            return self.browse()
        return self.filtered(lambda amenity: all(amenity in room.amenity_ids for room in rooms))
