def migrate(cr, version):
    # L'interrupteur « En maintenance » devient le champ « État technique » :
    # on reprend sa valeur avant que « maintenance » ne devienne calculé.
    cr.execute("""
        ALTER TABLE hotel_room ADD COLUMN IF NOT EXISTS technical_state varchar;
        UPDATE hotel_room
           SET technical_state = CASE WHEN maintenance THEN 'maintenance'
                                      ELSE 'in_service' END
         WHERE technical_state IS NULL;
        UPDATE hotel_room
           SET maintenance = technical_state <> 'in_service';
    """)
