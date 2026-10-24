from odoo import SUPERUSER_ID, api

# Types d'hôtel d'origine -> types d'auberge (mêmes identifiants XML,
# les chambres restent rattachées à leur type).
ROOM_TYPES = {
    'room_type_single': {
        'name': "Dortoir mixte", 'code': 'DORM-M', 'sequence': 1,
        'rental_mode': 'bed', 'list_price': 2000, 'default_capacity': 6,
        'description': "Dortoir mixte, location au lit.",
    },
    'room_type_suite': {
        'name': "Dortoir femmes", 'code': 'DORM-F', 'sequence': 2,
        'rental_mode': 'bed', 'list_price': 2000, 'default_capacity': 6,
        'description': "Dortoir réservé aux femmes, location au lit.",
    },
    'room_type_double': {
        'name': "Chambre privée", 'code': 'PRIV', 'sequence': 3,
        'rental_mode': 'room', 'list_price': 6000, 'default_capacity': 2,
        'description': "Chambre privée pour 1 à 2 personnes.",
    },
    'room_type_family': {
        'name': "Chambre familiale", 'code': 'FAM', 'sequence': 4,
        'rental_mode': 'both', 'list_price': 10000, 'default_capacity': 4,
        'description': "Chambre familiale, louable entière ou au lit.",
    },
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, vals in ROOM_TYPES.items():
        room_type = env.ref('hotel_management.%s' % xmlid, raise_if_not_found=False)
        if not room_type:
            continue
        room_type.write(vals)
        # Les chambres existantes adoptent le mode de location de leur type
        env['hotel.room'].with_context(active_test=False).search(
            [('room_type_id', '=', room_type.id)]).write(
                {'rental_mode': vals['rental_mode']})

    # Le tarif haute saison d'exemple portait sur la Suite (devenue dortoir)
    season = env.ref('hotel_management.season_summer_2026', raise_if_not_found=False)
    family = env.ref('hotel_management.room_type_family', raise_if_not_found=False)
    if season and family and season.room_type_id == env.ref(
            'hotel_management.room_type_suite', raise_if_not_found=False):
        season.write({'room_type_id': family.id, 'price': 12000})
