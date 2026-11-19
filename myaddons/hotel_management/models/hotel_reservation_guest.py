from odoo import api, fields, models, _


class HotelReservationGuest(models.Model):
    """Personne accompagnant le client principal d'une réservation.

    Le client principal (partner_id de la réservation) est l'« Adulte 1 » ;
    une fiche est tenue pour chaque autre adulte et chaque enfant. Les fiches
    suivent automatiquement les nombres d'adultes / d'enfants du séjour."""
    _name = 'hotel.reservation.guest'
    _description = "Personne de la réservation"
    _order = 'reservation_id, guest_type, position, id'

    reservation_id = fields.Many2one(
        'hotel.reservation', string="Réservation", required=True,
        ondelete='cascade', index=True)
    guest_type = fields.Selection([
        ('adult', 'Adulte'),
        ('child', 'Enfant'),
    ], string="Type", required=True, default='adult')
    position = fields.Integer(
        string="N°", help="Rang de la personne : Adulte 2, 3… (l'adulte 1 est "
                         "le client de la réservation), Enfant 1, 2…")
    label = fields.Char(string="Personne", compute='_compute_label')
    partner_id = fields.Many2one(
        'res.partner', string="Contact existant",
        help="Facultatif : reprend les informations d'un client déjà connu.")
    last_name = fields.Char(string="Nom")
    first_name = fields.Char(string="Prénom")
    name = fields.Char(string="Nom complet", compute='_compute_name', store=True)
    birthdate = fields.Date(string="Date de naissance")
    phone = fields.Char(string="Téléphone")
    id_type = fields.Selection(
        selection=lambda self: self.env['res.partner']._fields['hotel_id_type'].selection,
        string="Type de pièce d'identité")
    id_number = fields.Char(string="N° de pièce d'identité")
    id_document = fields.Binary(string="Scan pièce d'identité", attachment=True)
    id_document_name = fields.Char(string="Nom du fichier")
    state = fields.Selection(related='reservation_id.state')

    @api.depends('guest_type')
    def _compute_label(self):
        labels = dict(self._fields['guest_type'].selection)
        for guest in self:
            guest.label = labels.get(guest.guest_type, '')

    @api.depends('last_name', 'first_name')
    def _compute_name(self):
        for guest in self:
            guest.name = ' '.join(
                p.strip() for p in (guest.last_name, guest.first_name) if p and p.strip())

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        partner = self.partner_id
        if not partner:
            return
        self.last_name = partner.hotel_last_name or (
            partner.name if not partner.hotel_first_name else self.last_name)
        self.first_name = partner.hotel_first_name or self.first_name
        self.birthdate = partner.hotel_birthdate or self.birthdate
        self.phone = partner.phone or self.phone
        self.id_type = partner.hotel_id_type or self.id_type
        self.id_number = partner.hotel_id_number or self.id_number
