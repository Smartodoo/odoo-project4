def migrate(cr, version):
    """Initialise les nouveaux prix (room_price / bed_price) à partir de
    l'ancien modèle de tarification, pour les chambres déjà créées :
      - room_price : somme des prix des lits actifs, sinon l'ancien « price ».
      - bed_price  : prix minimum d'un lit actif, sinon l'ancien « price ».
    On ne touche qu'aux valeurs encore nulles / à zéro."""
    # Prix chambre = somme des prix des lits actifs
    cr.execute("""
        UPDATE hotel_room r
           SET room_price = sub.sump
          FROM (SELECT room_id, SUM(price) AS sump
                  FROM hotel_bed
                 WHERE active IS TRUE
                 GROUP BY room_id) sub
         WHERE r.id = sub.room_id
           AND COALESCE(r.room_price, 0) = 0
           AND COALESCE(sub.sump, 0) <> 0
    """)
    # Chambres sans lit : prix chambre = ancien prix fixe
    cr.execute("""
        UPDATE hotel_room
           SET room_price = COALESCE(price, 0)
         WHERE COALESCE(room_price, 0) = 0
    """)
    # Prix lit = prix minimum d'un lit actif
    cr.execute("""
        UPDATE hotel_room r
           SET bed_price = sub.minp
          FROM (SELECT room_id, MIN(price) AS minp
                  FROM hotel_bed
                 WHERE active IS TRUE
                 GROUP BY room_id) sub
         WHERE r.id = sub.room_id
           AND COALESCE(r.bed_price, 0) = 0
           AND COALESCE(sub.minp, 0) <> 0
    """)
    # À défaut, prix lit = ancien prix fixe
    cr.execute("""
        UPDATE hotel_room
           SET bed_price = COALESCE(price, 0)
         WHERE COALESCE(bed_price, 0) = 0
    """)
