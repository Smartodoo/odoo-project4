from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Location « par lit » : une ligne de réservation = un lit (champ `bed_id`).
    - lignes à un seul lit : `bed_id` renseigné ;
    - lignes à plusieurs lits : découpées en une ligne par lit (prix réparti) ;
    - lignes « par chambre » : tous les lits de la chambre y sont rattachés."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Line = env['hotel.reservation.line'].with_context(active_test=False)
    for line in Line.search([('booking_type', '=', 'bed')]):
        beds = line.bed_ids
        if not beds:
            continue
        unit = line.price_unit / len(beds)
        line.write({'bed_id': beds[0].id, 'bed_ids': [(6, 0, beds[0].ids)],
                    'price_unit': unit})
        for bed in beds[1:]:
            line.copy({'reservation_id': line.reservation_id.id, 'bed_id': bed.id,
                       'bed_ids': [(6, 0, bed.ids)], 'price_unit': unit})
    Line.search([('booking_type', '=', 'room')])._force_room_beds()
