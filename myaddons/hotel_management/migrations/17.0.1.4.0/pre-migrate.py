"""Suppression du mode de location « both » (Chambre entière ou au lit).

Les chambres et types encore en 'both' sont basculés en 'bed' (au lit), afin de
préserver leurs lits. Exécuté avant le rechargement du module pour qu'aucune
ligne ne conserve une valeur de sélection devenue invalide.
"""


def migrate(cr, version):
    for table in ('hotel_room', 'hotel_room_type'):
        cr.execute(
            "UPDATE %s SET rental_mode = 'bed' WHERE rental_mode = 'both'"
            % table)
