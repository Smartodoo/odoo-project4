def migrate(cr, version):
    """Ménage des lits : chaque lit reprend l'état de ménage actuel de sa
    chambre (une chambre « À nettoyer » a ses lits « À nettoyer »)."""
    cr.execute("""
        UPDATE hotel_bed b
           SET housekeeping_status = CASE r.housekeeping_status
                   WHEN 'clean' THEN 'clean' ELSE r.housekeeping_status END
          FROM hotel_room r
         WHERE r.id = b.room_id
           AND r.housekeeping_status IS NOT NULL
    """)
