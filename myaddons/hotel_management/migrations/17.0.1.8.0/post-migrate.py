def migrate(cr, version):
    """Nouveau champ « Afficher sur l'accueil » : on masque une seule fois de la
    section Confort de la page d'accueil le mini-bar, le balcon, la baignoire et
    le petit-déjeuner (les autres équipements restent affichés)."""
    cr.execute("""
        UPDATE hotel_amenity a
           SET website_home = FALSE
          FROM ir_model_data d
         WHERE d.model = 'hotel.amenity'
           AND d.module = 'hotel_management'
           AND d.res_id = a.id
           AND d.name IN ('amenity_minibar', 'amenity_balcony',
                          'amenity_bathtub', 'amenity_breakfast')
    """)
