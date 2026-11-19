def migrate(cr, version):
    """L'étage (texte libre) devient un lien vers « Étages » : on met de côté
    l'ancienne valeur avant que la colonne ne soit recalculée."""
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'hotel_room' AND column_name = 'floor'
    """)
    if cr.fetchone():
        cr.execute("ALTER TABLE hotel_room RENAME COLUMN floor TO floor_legacy")
