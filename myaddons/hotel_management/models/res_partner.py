from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    hotel_last_name = fields.Char(string="Nom de famille")
    hotel_first_name = fields.Char(string="Prénom")
    hotel_id_type = fields.Selection([
        ('cni', "Carte nationale d'identité"),
        ('passport', "Passeport"),
        ('driving_license', "Permis de conduire"),
        ('residence', "Carte de séjour"),
        ('other', "Autre"),
    ], string="Type de pièce d'identité")
    hotel_id_number = fields.Char(string="N° de pièce d'identité")
    hotel_birthdate = fields.Date(string="Date de naissance")

    hotel_id_document = fields.Binary(
        string="Scan de la pièce d'identité", attachment=True,
        help="Photo ou scan de la pièce d'identité (enregistrée au check-in).")
    hotel_id_document_name = fields.Char(string="Nom du fichier pièce d'identité")
    hotel_note = fields.Text(string="Observations (Auberge)")
    hotel_customer_type_id = fields.Many2one(
        'hotel.customer.type', string="Type de client", tracking=True,
        ondelete='restrict')
    hotel_is_blacklisted = fields.Boolean(
        related='hotel_customer_type_id.is_blacklist', string="Client en alerte")
    hotel_customer_type_name = fields.Char(
        related='hotel_customer_type_id.name', string="Libellé type de client")
    hotel_preferences = fields.Text(
        string="Préférences",
        help="Préférences du client : chambre (étage, lit, calme…), "
             "consommations, petit-déjeuner, etc.")

    # Conditions tarifaires du client (cahier des charges §5)
    hotel_special_room_price = fields.Monetary(
        string="Tarif spécial chambre / nuit", currency_field='hotel_currency_id',
        help="Si renseigné, remplace le prix normal (et saisonnier) d'une nuit "
             "en chambre entière pour ce client.")
    hotel_special_bed_price = fields.Monetary(
        string="Tarif spécial lit / nuit", currency_field='hotel_currency_id',
        help="Si renseigné, remplace le prix normal (et saisonnier) d'une nuit "
             "pour un lit, pour ce client.")
    hotel_currency_id = fields.Many2one(
        'res.currency', compute='_compute_hotel_currency_id')

    hotel_reservation_ids = fields.One2many(
        'hotel.reservation', 'partner_id', string="Réservations")
    hotel_reservation_count = fields.Integer(
        string="Nb réservations", compute='_compute_hotel_reservation_count')
    hotel_payment_count = fields.Integer(
        string="Nb paiements auberge", compute='_compute_hotel_payment_count')
    hotel_amount_due = fields.Monetary(
        string="Impayé auberge", currency_field='hotel_currency_id',
        compute='_compute_hotel_payment_count')

    def _compute_hotel_currency_id(self):
        for partner in self:
            partner.hotel_currency_id = self.env.company.currency_id

    def _compute_hotel_payment_count(self):
        Payment = self.env['account.payment'].sudo()
        Reservation = self.env['hotel.reservation'].sudo()
        for partner in self:
            if not partner.id:
                partner.hotel_payment_count = 0
                partner.hotel_amount_due = 0.0
                continue
            partner.hotel_payment_count = Payment.search_count([
                ('hotel_reservation_id.partner_id', '=', partner.id)])
            partner.hotel_amount_due = sum(Reservation.search([
                ('partner_id', '=', partner.id),
                ('state', 'in', ('checkin', 'checkout')),
            ]).mapped('amount_due'))

    def action_view_hotel_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Paiements — %s" % self.display_name,
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('hotel_reservation_id.partner_id', '=', self.id)],
            'context': {'create': False},
        }

    @api.model
    def _hotel_full_name(self, last_name, first_name):
        return ' '.join(p.strip() for p in (last_name, first_name) if p and p.strip())

    @api.constrains('hotel_birthdate')
    def _check_hotel_birthdate(self):
        """Le client qui réserve doit être majeur (18 ans révolus)."""
        today = fields.Date.context_today(self)
        for partner in self.filtered('hotel_birthdate'):
            if partner.hotel_birthdate > today:
                raise ValidationError(
                    _("La date de naissance ne peut pas être dans le futur."))
            if relativedelta(today, partner.hotel_birthdate).years < 18:
                raise ValidationError(_(
                    "%s doit avoir au moins 18 ans pour réserver.",
                    partner.display_name))

    @api.model
    def _hotel_find_id_number(self, number, exclude=None):
        """Contact (actif) ayant déjà ce n° de pièce d'identité (casse et
        espaces de début/fin ignorés), hors `exclude`."""
        number = (number or '').strip()
        if not number:
            return self.browse()
        escaped = number.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        domain = [('hotel_id_number', '=ilike', escaped)]
        if exclude:
            domain.append(('id', 'not in', exclude.ids))
        return self.search(domain, limit=1)

    @api.model
    def _hotel_id_number_message(self, number, existing):
        return _(
            "Ce contact existe déjà avec la pièce d'identité n° %(number)s : "
            "%(name)s.\n\nSélectionnez le contact existant au lieu d'en créer "
            "un nouveau, ou corrigez le numéro.",
            number=number.strip(), name=existing.display_name)

    @api.constrains('hotel_id_number')
    def _check_hotel_id_number_unique(self):
        for partner in self.filtered('hotel_id_number'):
            existing = self._hotel_find_id_number(partner.hotel_id_number, exclude=partner)
            if existing:
                raise ValidationError(
                    self._hotel_id_number_message(partner.hotel_id_number, existing))

    @api.onchange('hotel_id_number')
    def _onchange_hotel_id_number(self):
        existing = self._hotel_find_id_number(self.hotel_id_number, exclude=self._origin)
        if existing:
            return {'warning': {
                'title': _("Pièce d'identité déjà enregistrée"),
                'message': self._hotel_id_number_message(self.hotel_id_number, existing)}}

    @api.onchange('hotel_last_name', 'hotel_first_name')
    def _onchange_hotel_names(self):
        full = self._hotel_full_name(self.hotel_last_name, self.hotel_first_name)
        if full:
            self.name = full

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                full = self._hotel_full_name(
                    vals.get('hotel_last_name'), vals.get('hotel_first_name'))
                if full:
                    vals['name'] = full
        return super().create(vals_list)

    def write(self, vals):
        # Nom / prénom saisis séparément (ex. depuis une réservation) :
        # le nom complet du contact suit.
        if ('hotel_last_name' in vals or 'hotel_first_name' in vals) and 'name' not in vals:
            for partner in self:
                full = self._hotel_full_name(
                    vals.get('hotel_last_name', partner.hotel_last_name),
                    vals.get('hotel_first_name', partner.hotel_first_name))
                super(ResPartner, partner).write(dict(vals, name=full) if full else vals)
            return True
        return super().write(vals)

    def _compute_hotel_reservation_count(self):
        groups = self.env['hotel.reservation']._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count'])
        mapping = {partner.id: count for partner, count in groups}
        for rec in self:
            rec.hotel_reservation_count = mapping.get(rec.id, 0)

    def action_view_hotel_reservations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Réservations",
            'res_model': 'hotel.reservation',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
