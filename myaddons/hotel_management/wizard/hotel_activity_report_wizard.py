from datetime import timedelta

from odoo import fields, models, _
from odoo.exceptions import UserError

from ..models.account_payment import HOTEL_PAYMENT_MODES


class HotelActivityReportWizard(models.TransientModel):
    """Rapport d'activité / chiffre d'affaires sur une période choisie
    (cahier des charges §15 « CA par le choix des dates » et §19)."""
    _name = 'hotel.activity.report.wizard'
    _description = "Rapport d'activité de l'auberge"

    date_from = fields.Date(
        string="Du", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        string="Au", required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    def _check(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_("La date de fin doit être postérieure à la date de début."))

    def action_print(self):
        self._check()
        return self.env.ref(
            'hotel_management.action_report_hotel_activity').report_action(self)

    def action_analyze(self):
        self._check()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Chiffre d'affaires du %(a)s au %(b)s",
                      a=self.date_from, b=self.date_to),
            'res_model': 'hotel.revenue.report',
            'view_mode': 'pivot,graph,list',
            'domain': [('date', '>=', self.date_from), ('date', '<=', self.date_to),
                       ('company_id', '=', self.company_id.id)],
            'context': {'pivot_measures': ['amount', 'room_nights', 'bed_nights']},
        }

    def get_report_data(self):
        """Chiffres du rapport PDF."""
        self.ensure_one()
        Report = self.env['hotel.revenue.report'].sudo()
        domain = [('date', '>=', self.date_from), ('date', '<=', self.date_to),
                  ('company_id', '=', self.company_id.id)]
        nights = Report.search(domain)
        days = (self.date_to - self.date_from).days + 1

        rooms = self.env['hotel.room'].sudo().search(
            [('company_id', '=', self.company_id.id)])
        sellable = rooms.filtered(lambda r: not r.maintenance)
        total_beds = sum(len(r.bed_ids.filtered('active')) for r in sellable)
        room_nights = sum(nights.mapped('room_nights'))
        bed_nights = sum(nights.mapped('bed_nights'))
        revenue = sum(nights.mapped('amount'))

        reservations = self.env['hotel.reservation'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ('confirmed', 'checkin', 'checkout')),
            ('checkin', '<=', self.date_to), ('checkout', '>', self.date_from),
        ])
        services = self.env['hotel.reservation.service'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ('confirmed', 'checkin', 'checkout')),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
        ])
        payments = self.env['account.payment'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('hotel_reservation_id', '!=', False),
            ('state', 'in', ('paid', 'reconciled')),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
        ])
        by_mode = []
        for mode, label in HOTEL_PAYMENT_MODES:
            amount = sum(payments.filtered(
                lambda p: p.hotel_payment_mode == mode).mapped('amount_company_currency_signed'))
            by_mode.append((label, amount))

        def group(field, label_of):
            totals = {}
            for row in nights:
                key = row[field]
                entry = totals.setdefault(key, [0.0, 0.0])
                entry[0] += row.amount
                entry[1] += row.room_nights
            return sorted(
                [(label_of(k), v[0], v[1]) for k, v in totals.items()],
                key=lambda t: -t[1])

        source_labels = dict(Report._fields['source'].selection)
        by_day = []
        for n in range(days):
            day = self.date_from + timedelta(days=n)
            rows = nights.filtered(lambda r: r.date == day)
            by_day.append((day, sum(rows.mapped('amount')), sum(rows.mapped('room_nights'))))

        return {
            'days': days,
            'revenue': revenue,
            'services': sum(services.mapped('price_subtotal')),
            'collected': sum(payments.mapped('amount_company_currency_signed')),
            'unpaid': sum(reservations.filtered(
                lambda r: r.state in ('checkin', 'checkout')).mapped('amount_due')),
            'room_nights': room_nights,
            'bed_nights': bed_nights,
            'occupancy_rooms': (room_nights * 100.0 / (len(sellable) * days))
            if sellable and days else 0.0,
            'occupancy_beds': (bed_nights * 100.0 / (total_beds * days))
            if total_beds and days else 0.0,
            'reservation_count': len(reservations),
            'guest_count': len(reservations.mapped('partner_id')),
            'avg_stay': (sum(reservations.mapped('nights')) / len(reservations))
            if reservations else 0.0,
            'by_mode': by_mode,
            'by_source': group('source', lambda k: source_labels.get(k, k or '-')),
            'by_room': group('room_id', lambda k: k.display_name or '-'),
            'by_type': group('room_type_id', lambda k: k.display_name or '-'),
            'by_day': by_day,
        }
