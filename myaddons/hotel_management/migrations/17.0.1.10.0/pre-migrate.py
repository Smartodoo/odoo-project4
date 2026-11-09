def migrate(cr, version):
    """L'acompte n'est plus saisi à la main : il devient la somme des
    paiements réellement encaissés. On garde une trace des anciens montants
    saisis, pour les signaler dans le chatter (cf. post-migrate)."""
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'hotel_reservation' AND column_name = 'deposit_amount'
    """)
    if not cr.fetchone():
        return
    cr.execute("DROP TABLE IF EXISTS hotel_legacy_deposit")
    cr.execute("""
        CREATE TABLE hotel_legacy_deposit AS
        SELECT id AS reservation_id, deposit_amount AS amount
          FROM hotel_reservation
         WHERE COALESCE(deposit_amount, 0) <> 0
    """)
