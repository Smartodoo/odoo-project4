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

    _sql_constraints = [
        ('price_positive', 'CHECK(price > 0)',
         "Le tarif saisonnier doit être strictement positif."),
    ]

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError(
                    _("La date de fin doit être postérieure ou égale à la date de début."))

    @api.constrains('date_start', 'date_end', 'room_type_id', 'active', 'company_id')
    def _check_no_overlap(self):
        """Deux tarifs ne doivent pas se chevaucher sur le même périmètre
        (même type de chambre — ou tous deux globaux — et même société),
        sinon le prix appliqué à une date deviendrait ambigu."""
        for rec in self.filtered('active'):
            if not (rec.date_start and rec.date_end):
                continue
            domain = [
                ('id', '!=', rec.id),
                ('active', '=', True),
                ('company_id', '=', rec.company_id.id),
                ('room_type_id', '=', rec.room_type_id.id if rec.room_type_id else False),
                ('date_start', '<=', rec.date_end),
                ('date_end', '>=', rec.date_start),
            ]
            overlap = self.search(domain, limit=1)
            if overlap:
                raise ValidationError(_(
                    "Le tarif « %(a)s » (%(a1)s → %(a2)s) chevauche « %(b)s » "
                    "(%(b1)s → %(b2)s) pour le même périmètre.\n\n"
                    "Ajustez les dates ou désactivez l'un des deux tarifs.",
                    a=rec.name, a1=rec.date_start, a2=rec.date_end,
                    b=overlap.name, b1=overlap.date_start, b2=overlap.date_end))
