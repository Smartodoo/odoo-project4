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

    # Champ de la fiche personne -> champ du contact (même fiche client que
    # pour le client principal de la réservation)
    _PARTNER_FIELDS = {
        'last_name': 'hotel_last_name',
        'first_name': 'hotel_first_name',
        'birthdate': 'hotel_birthdate',
        'phone': 'phone',
        'id_type': 'hotel_id_type',
        'id_number': 'hotel_id_number',
        'id_document': 'hotel_id_document',
        'id_document_name': 'hotel_id_document_name',
    }

    def _partner_vals_from(self, values):
        return {self._PARTNER_FIELDS[k]: v for k, v in values.items()
                if k in self._PARTNER_FIELDS and v}

    @api.onchange('last_name', 'first_name')
    def _onchange_names_create_partner(self):
        """Nouvelle personne : dès que nom ET prénom sont saisis (sans contact
        choisi), le contact est créé et sélectionné."""
        # Adultes seulement : un contact doit avoir 18 ans (règle des contacts
        # de l'auberge) ; les enfants restent sur leur fiche de séjour.
        if self.guest_type != 'adult' or self.partner_id \
                or not (self.last_name and self.first_name):
            return
        values = {}
        for fname in self._PARTNER_FIELDS:
            values[fname] = self[fname]
        self.partner_id = self.env['res.partner'].create(self._partner_vals_from(values))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Nom saisi sans contact (ex. homonyme confirmé) : contact créé ici
            if vals.get('guest_type', 'adult') == 'adult' and not vals.get('partner_id') \
                    and (vals.get('last_name') or vals.get('first_name')):
                vals['partner_id'] = self.env['res.partner'].create(
                    self._partner_vals_from(vals)).id
        guests = super().create(vals_list)
        for guest, vals in zip(guests, vals_list):
            guest._push_to_partner(vals)
        return guests

    def write(self, vals):
        res = super().write(vals)
        for guest in self.filtered(lambda g: g.guest_type == 'adult'):
            if not guest.partner_id and (guest.last_name or guest.first_name):
                guest.partner_id = self.env['res.partner'].create(guest._partner_vals_from(
                    {f: guest[f] for f in self._PARTNER_FIELDS}))
            else:
                guest._push_to_partner(vals)
        return res

    def _push_to_partner(self, vals):
        """Informations saisies sur la fiche personne recopiées sur le contact."""
        self.ensure_one()
        partner_vals = self._partner_vals_from(vals)
        if self.guest_type == 'adult' and self.partner_id and partner_vals:
            self.partner_id.write(partner_vals)
