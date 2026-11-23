from odoo import _, fields, models


class HotelCustomerType(models.Model):
    """Type de client (fidèle, VIP, liste noire…), paramétrable en configuration."""
    _name = 'hotel.customer.type'
    _description = "Type de client"
    _order = 'sequence, name'

    name = fields.Char(string="Type de client", required=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string="Couleur")
    active = fields.Boolean(default=True)
    is_blacklist = fields.Boolean(
        string="Alerte rouge",
        help="Client à risque (ex. liste noire) : bandeau rouge sur la fiche "
             "client et sur ses réservations, avertissement à la sélection.")
    partner_ids = fields.One2many(
        'res.partner', 'hotel_customer_type_id', string="Clients")
    partner_count = fields.Integer(
        string="Nb clients", compute='_compute_partner_count')

    _name_uniq = models.Constraint(
        'unique(name)', "Ce type de client existe déjà.")

    def _compute_partner_count(self):
        groups = self.env['res.partner']._read_group(
            [('hotel_customer_type_id', 'in', self.ids)],
            ['hotel_customer_type_id'], ['__count'])
        mapping = {t.id: count for t, count in groups}
        for rec in self:
            rec.partner_count = mapping.get(rec.id, 0)

    def action_view_partners(self):
        """Contacts ayant ce type de client."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Clients « %s »", self.name),
            'res_model': 'res.partner',
            'view_mode': 'list,kanban,form',
            'domain': [('hotel_customer_type_id', '=', self.id)],
            'context': {'default_hotel_customer_type_id': self.id},
        }
