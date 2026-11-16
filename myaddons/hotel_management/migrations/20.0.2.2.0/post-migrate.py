from odoo import api, SUPERUSER_ID

MAX = 3


def migrate(cr, version):
    """Capacité maximale d'une chambre = 3 places : chambres et types existants
    ramenés à 3. Les lits en trop sont retirés par la logique standard
    (_remove_extra_beds : jamais réservé -> supprimé, historique -> archivé,
    réservation en cours / à venir -> erreur, la migration s'arrête)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['hotel.room.type'].with_context(active_test=False).search(
        [('default_capacity', '>', MAX)]).write({'default_capacity': MAX})
    env['hotel.room'].with_context(active_test=False).search(
        [('capacity', '>', MAX)]).write({'capacity': MAX})
