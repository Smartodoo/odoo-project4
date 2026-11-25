def migrate(cr, version):
    """Nouveau champ « Étage » des réservations : repris de l'étage de la
    première chambre de chaque réservation."""
    cr.execute("""
        UPDATE hotel_reservation res
           SET floor_id = sub.floor_id
          FROM (SELECT DISTINCT ON (l.reservation_id)
                       l.reservation_id, room.floor_id
                  FROM hotel_reservation_line l
                  JOIN hotel_room room ON room.id = l.room_id
                 WHERE room.floor_id IS NOT NULL
                 ORDER BY l.reservation_id, l.id) sub
         WHERE res.id = sub.reservation_id AND res.floor_id IS NULL
    """)
