from odoo import fields, models, tools
from odoo.tools import SQL


class HotelRevenueReport(models.Model):
    """Analyse du chiffre d'affaires hébergement (cahier des charges §15) :
    une ligne par NUIT et par lit (ou par chambre sans lit) réservé. Permet
    le CA par jour, par mois, sur une période choisie, par chambre, par lit,
    par type et par source de réservation, et le nombre de nuitées."""
    _name = 'hotel.revenue.report'
    _description = "Analyse du chiffre d'affaires de l'auberge"
    _auto = False
    _order = 'date desc'

    date = fields.Date(string="Nuit du", readonly=True)
    reservation_id = fields.Many2one('hotel.reservation', string="Réservation", readonly=True)
    partner_id = fields.Many2one('res.partner', string="Client", readonly=True)
    room_id = fields.Many2one('hotel.room', string="Chambre", readonly=True)
    room_type_id = fields.Many2one('hotel.room.type', string="Type de chambre", readonly=True)
    bed_id = fields.Many2one('hotel.bed', string="Lit", readonly=True)
    booking_type = fields.Selection([
        ('room', 'Par chambre'),
        ('bed', 'Par lit'),
    ], string="Type de location", readonly=True)
    source = fields.Selection([
        ('direct', 'Direct'),
        ('phone', 'Téléphone'),
        ('website', 'Site web'),
        ('booking', 'Booking / plateforme en ligne'),
        ('agency', 'Agence'),
        ('walkin', 'Sans réservation'),
        ('other', 'Autre'),
    ], string="Source", readonly=True)
    state = fields.Selection([
        ('confirmed', 'Confirmée'),
        ('checkin', 'Enregistrée'),
        ('checkout', 'Terminée'),
    ], string="État", readonly=True)
    company_id = fields.Many2one('res.company', string="Société", readonly=True)
    currency_id = fields.Many2one('res.currency', string="Devise", readonly=True)
    amount = fields.Monetary(
        string="CA hébergement (HT)", readonly=True, currency_field='currency_id',
        help="Prix de la nuit, remise du séjour déduite, réparti entre les lits.")
    room_nights = fields.Float(
        string="Nuitées chambre", readonly=True, digits=(16, 2),
        help="Nombre de nuits-chambre vendues (une chambre louée une nuit = 1).")
    bed_nights = fields.Float(
        string="Nuitées lit", readonly=True, digits=(16, 2),
        help="Nombre de nuits-lit vendues.")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("CREATE OR REPLACE VIEW %s AS (%s)",
                                SQL.identifier(self._table), self._revenue_query()))

    def _revenue_query(self):
        return SQL("""
            WITH beds AS (
                SELECT rel.hotel_reservation_line_id AS line_id,
                       rel.hotel_bed_id AS bed_id,
                       COUNT(*) OVER (PARTITION BY rel.hotel_reservation_line_id) AS nb
                  FROM hotel_bed_hotel_reservation_line_rel rel
            )
            SELECT ROW_NUMBER() OVER (ORDER BY l.id, night.d, b.bed_id) AS id,
                   night.d::date AS date,
                   l.reservation_id,
                   r.partner_id,
                   l.room_id,
                   room.room_type_id,
                   b.bed_id,
                   r.booking_type,
                   r.source,
                   r.state,
                   r.company_id,
                   r.currency_id,
                   (l.price_subtotal / NULLIF(l.nights, 0))
                     * (CASE WHEN COALESCE(r.amount_gross, 0) > 0
                             THEN 1 - COALESCE(r.amount_discount, 0) / r.amount_gross
                             ELSE 1 END)
                     / COALESCE(b.nb, 1) AS amount,
                   1.0 / COALESCE(b.nb, 1) AS room_nights,
                   CASE WHEN b.bed_id IS NULL THEN 0 ELSE 1 END AS bed_nights
              FROM hotel_reservation_line l
              JOIN hotel_reservation r ON r.id = l.reservation_id
              JOIN hotel_room room ON room.id = l.room_id
              CROSS JOIN LATERAL generate_series(
                    l.checkin::timestamp, (l.checkout - 1)::timestamp, interval '1 day'
              ) AS night(d)
              LEFT JOIN beds b ON b.line_id = l.id
             WHERE r.state IN ('confirmed', 'checkin', 'checkout')
               AND l.checkout > l.checkin
        """)
