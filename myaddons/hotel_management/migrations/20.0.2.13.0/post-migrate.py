import re

from odoo import SUPERUSER_ID, api


def _sort_key(name):
    numbers = re.findall(r'\d+', name)
    return (int(numbers[0]) if numbers else 999, name)


def migrate(cr, version):
    """Crée un étage par valeur distincte saisie sur les chambres (déjà créés
    par les données du module : réutilisés) et y rattache les chambres."""
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'hotel_room' AND column_name = 'floor_legacy'
    """)
    if not cr.fetchone():
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Floor = env['hotel.floor'].with_context(active_test=False)
    cr.execute("""SELECT id, btrim(floor_legacy) FROM hotel_room
                   WHERE floor_legacy IS NOT NULL AND btrim(floor_legacy) != ''""")
    rows = cr.fetchall()
    for name in sorted({name for _id, name in rows}, key=_sort_key):
        if not Floor.search([('name', '=', name)], limit=1):
            Floor.create({'name': name, 'sequence': _sort_key(name)[0] * 10})
    for room_id, name in rows:
        floor = Floor.search([('name', '=', name)], limit=1)
        env['hotel.room'].browse(room_id).floor_id = floor
    cr.execute("ALTER TABLE hotel_room DROP COLUMN floor_legacy")
