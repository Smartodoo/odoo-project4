def migrate(cr, version):
    """Prix déplacés de la chambre vers le type de chambre (choisi dans la
    réservation) ; type, mode de location et prix retirés des chambres ;
    mode de location et capacité retirés des types.

    - type.room_price = prix chambre des chambres du type, sinon l'ancien
      « Prix / nuit » du type ;
    - type.bed_price  = prix lit des chambres louées au lit du type, sinon 0 ;
    - réservations sans type : type de leurs chambres (le prix déjà calculé
      des lignes est conservé) ;
    - colonnes obligatoires des champs supprimés : NOT NULL levé (sinon la
      création d'une chambre / d'un type échoue).
    """
    cr.execute("SELECT 1 FROM information_schema.columns "
               "WHERE table_name = 'hotel_room' AND column_name = 'room_type_id'")
    if not cr.fetchone():
        return
    cr.execute("""
        ALTER TABLE hotel_room_type ADD COLUMN IF NOT EXISTS room_price numeric;
        ALTER TABLE hotel_room_type ADD COLUMN IF NOT EXISTS bed_price numeric;
        UPDATE hotel_room_type t
           SET room_price = COALESCE(
                   (SELECT MAX(r.room_price) FROM hotel_room r
                     WHERE r.room_type_id = t.id AND r.room_price > 0),
                   t.list_price, 0),
               bed_price = COALESCE(
                   (SELECT MAX(r.bed_price) FROM hotel_room r
                     WHERE r.room_type_id = t.id AND r.rental_mode = 'bed'
                       AND r.bed_price > 0), 0);
        UPDATE hotel_reservation res
           SET room_type_id = sub.type_id
          FROM (SELECT DISTINCT ON (l.reservation_id)
                       l.reservation_id, room.room_type_id AS type_id
                  FROM hotel_reservation_line l
                  JOIN hotel_room room ON room.id = l.room_id
                 ORDER BY l.reservation_id, l.id) sub
         WHERE res.id = sub.reservation_id AND res.room_type_id IS NULL;
        UPDATE hotel_reservation_line l
           SET room_type_id = res.room_type_id
          FROM hotel_reservation res
         WHERE res.id = l.reservation_id;
        ALTER TABLE hotel_room ALTER COLUMN room_type_id DROP NOT NULL;
        ALTER TABLE hotel_room ALTER COLUMN rental_mode DROP NOT NULL;
        ALTER TABLE hotel_room ALTER COLUMN whole_room_pricing DROP NOT NULL;
        ALTER TABLE hotel_room_type ALTER COLUMN rental_mode DROP NOT NULL;
    """)
