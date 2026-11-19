from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Chambres louées au lit : prix chambre = somme des prix des lits."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['hotel.room'].with_context(active_test=False).search(
        [('rental_mode', '=', 'bed')])._sync_bed_room_price()
