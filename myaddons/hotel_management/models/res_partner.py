from odoo import api, fields, models


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

    hotel_reservation_ids = fields.One2many(
        'hotel.reservation', 'partner_id', string="Réservations")
    hotel_reservation_count = fields.Integer(
        string="Nb réservations", compute='_compute_hotel_reservation_count')

    @api.model
    def _hotel_full_name(self, last_name, first_name):
        return ' '.join(p.strip() for p in (last_name, first_name) if p and p.strip())

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
        groups = self.env['hotel.reservation'].read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['partner_id'])
        mapping = {g['partner_id'][0]: g['partner_id_count'] for g in groups}
        for rec in self:
            rec.hotel_reservation_count = mapping.get(rec.id, 0)

    def action_view_hotel_reservations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Réservations",
            'res_model': 'hotel.reservation',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
