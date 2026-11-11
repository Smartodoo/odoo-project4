from datetime import timedelta

from odoo import api, fields, models

WEEKDAYS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
STATE_LABELS = {
    'draft': 'Brouillon',
    'confirmed': 'Réservée',
    'checkin': 'Présent',
    'checkout': 'Parti',
}


class HotelPlanning(models.AbstractModel):
    """Données du planning graphique (cahier des charges §3.3) : chambres et
    lits en lignes, jours en colonnes, réservations en barres."""
    _name = 'hotel.planning'
    _description = "Planning des chambres et des lits"

    @api.model
    def get_planning_data(self, date_from=None, days=14):
        days = max(1, min(int(days or 14), 62))
        start = fields.Date.to_date(date_from) if date_from else \
            fields.Date.context_today(self)
        end = start + timedelta(days=days)
        today = fields.Date.context_today(self)

        rooms = self.env['hotel.room'].search([], order='floor, name')
        lines = self.env['hotel.reservation.line'].search([
            ('room_id', 'in', rooms.ids),
            ('state', 'in', ('draft', 'confirmed', 'checkin', 'checkout')),
            ('checkin', '<', end),
            ('checkout', '>', start),
        ])

        def span(line):
            first = max((line.checkin - start).days, 0)
            last = min((line.checkout - start).days, days)  # exclusif
            return first, last

        def booking(line):
            first, last = span(line)
            return {
                'line_id': line.id,
                'reservation_id': line.reservation_id.id,
                'name': line.reservation_id.name,
                'partner': line.partner_id.display_name or '',
                'state': line.state,
                'state_label': STATE_LABELS.get(line.state, line.state),
                'start': first,
                'end': last,
                'starts_before': line.checkin < start,
                'ends_after': line.checkout > end,
                'checkin': fields.Date.to_string(line.checkin),
                'checkout': fields.Date.to_string(line.checkout),
                'booking_type': line.booking_type,
                'beds': ', '.join(line.bed_ids.mapped('name')),
            }

        # Compteurs par jour : une chambre / un lit est « occupé » une nuit
        # donnée si une réservation active (confirmée ou client présent) la couvre.
        active_lines = lines.filtered(lambda l: l.state in ('confirmed', 'checkin'))
        sellable = rooms.filtered(lambda r: not r.maintenance)
        total_beds = sum(len(r.bed_ids.filtered('active')) for r in sellable)
        day_list = []
        for n in range(days):
            day = start + timedelta(days=n)
            night = active_lines.filtered(lambda l: l.checkin <= day < l.checkout)
            busy_rooms = night.mapped('room_id') & sellable
            busy_beds = set()
            for line in night:
                beds = (line.room_id.bed_ids.filtered('active')
                        if line.booking_type == 'room' else line.bed_ids)
                busy_beds.update(beds.ids)
            full_rooms = busy_rooms.filtered(
                lambda r: not r.bed_ids.filtered('active')
                or set(r.bed_ids.filtered('active').ids) <= busy_beds)
            day_list.append({
                'date': fields.Date.to_string(day),
                'weekday': WEEKDAYS[day.weekday()],
                'day': day.day,
                'month': day.month,
                'is_today': day == today,
                'is_weekend': day.weekday() >= 5,
                'rooms_busy': len(busy_rooms),
                'rooms_full': len(full_rooms),
                'rooms_free': len(sellable) - len(busy_rooms),
                'beds_busy': len(busy_beds),
                'beds_free': total_beds - len(busy_beds),
                'arrivals': len(lines.filtered(
                    lambda l: l.checkin == day and l.state in ('confirmed', 'checkin')
                ).mapped('reservation_id')),
                'departures': len(lines.filtered(
                    lambda l: l.checkout == day and l.state in ('checkin', 'checkout')
                ).mapped('reservation_id')),
            })

        room_rows = []
        for room in rooms:
            room_lines = lines.filtered(lambda l: l.room_id == room)
            beds = room.bed_ids.filtered('active')
            bed_rows = []
            # Dortoirs (location au lit) : une ligne par lit
            if room.rental_mode == 'bed' and beds:
                for bed in beds:
                    bed_lines = room_lines.filtered(
                        lambda l: l.booking_type == 'room' or bed in l.bed_ids)
                    bed_rows.append({
                        'id': bed.id,
                        'name': bed.name,
                        'status': bed.status,
                        'bookings': [booking(l) for l in bed_lines],
                    })
            room_rows.append({
                'id': room.id,
                'name': room.name,
                'floor': room.floor or '',
                'type': room.room_type_id.display_name or '',
                'rental_mode': room.rental_mode,
                'status': room.status,
                'status_label': dict(room._fields['status'].selection).get(room.status, ''),
                'housekeeping': room.housekeeping_status,
                'housekeeping_label': dict(
                    room._fields['housekeeping_status'].selection).get(
                    room.housekeeping_status, ''),
                'unavailable': room.maintenance,
                'bed_count': len(beds),
                'bookings': [] if bed_rows else [booking(l) for l in room_lines],
                'beds': bed_rows,
            })

        return {
            'date_from': fields.Date.to_string(start),
            'date_to': fields.Date.to_string(end - timedelta(days=1)),
            'days': day_list,
            'rooms': room_rows,
            'totals': {
                'rooms': len(rooms),
                'sellable_rooms': len(sellable),
                'beds': total_beds,
            },
        }
