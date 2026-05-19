from odoo import api, fields, models


class ReservationParking(models.Model):
    _name = 'commercial.reservation.parking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Réservation Parking'
    _rec_name = 'client_id'

    client_id = fields.Many2one('res.partner', string="Client", required=True, tracking=True)
    parking_id = fields.Many2one(
        'commercial.lot', string="Parking", tracking=True,
        domain="[('id', 'in', allowed_parking_ids)]")
    date_reservation = fields.Date(string="Date de réservation", default=fields.Date.today, tracking=True)
    modalite_paiement = fields.Text(string="Modalité de paiement")
    conditions = fields.Text(string="Conditions")

    # Related fields from parking_id
    projet_id = fields.Many2one('commercial.projet', string="Projet", related='parking_id.projet_id', store=True)
    bloc_id = fields.Many2one('commercial.bloc', string="Bloc", related='parking_id.bloc_id', store=True)
    etage_id = fields.Many2one('commercial.etage', string="Étage", related='parking_id.etage_id', store=True)

    # Computed: lots parking du client
    allowed_parking_ids = fields.Many2many(
        'commercial.lot', string="Parkings disponibles", compute='_compute_allowed_parking_ids')

    @api.depends('client_id', 'client_id.commercial_lot_ids')
    def _compute_allowed_parking_ids(self):
        for rec in self:
            if rec.client_id:
                rec.allowed_parking_ids = rec.client_id.commercial_lot_ids.filtered(
                    lambda l: l.categorie_id and l.categorie_id.type_lot_id
                    and 'PARK' in (l.categorie_id.type_lot_id.name or '').upper()
                )
                # Si aucun lot parking trouvé, afficher tous les lots du client
                if not rec.allowed_parking_ids:
                    rec.allowed_parking_ids = rec.client_id.commercial_lot_ids
            else:
                rec.allowed_parking_ids = self.env['commercial.lot']

    def action_print_fiche_parking(self):
        return self.env.ref('commercial.action_report_reservation_parking').report_action(self)
