def migrate(cr, version):
    """Le « Type de location » passe de la ligne à l'en-tête de réservation.
    On crée la colonne sur hotel_reservation et on la déduit des lignes
    existantes AVANT que le champ related ne recalcule les lignes, afin de ne
    pas perdre les réservations « par lit »."""
    cr.execute(
        "ALTER TABLE hotel_reservation ADD COLUMN IF NOT EXISTS booking_type varchar")
    # Au moins une ligne « par lit » -> réservation « par lit »
    cr.execute("""
        UPDATE hotel_reservation r
           SET booking_type = 'bed'
         WHERE EXISTS (SELECT 1
                         FROM hotel_reservation_line l
                        WHERE l.reservation_id = r.id
                          AND l.booking_type = 'bed')
    """)
    # Le reste -> « par chambre »
    cr.execute("""
        UPDATE hotel_reservation
           SET booking_type = 'room'
         WHERE booking_type IS NULL
    """)
