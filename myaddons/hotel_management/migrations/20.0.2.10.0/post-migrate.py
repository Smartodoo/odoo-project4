def migrate(cr, version):
    """Type « Liste noire » (données noupdate déjà créées) : alerte rouge."""
    cr.execute("""
        UPDATE hotel_customer_type t SET is_blacklist = TRUE
          FROM ir_model_data d
         WHERE d.model = 'hotel.customer.type' AND d.res_id = t.id
           AND d.module = 'hotel_management' AND d.name = 'customer_type_blacklist'
    """)
