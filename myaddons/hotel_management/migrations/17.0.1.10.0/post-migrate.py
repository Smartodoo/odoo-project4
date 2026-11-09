from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Recalcule Acompte / Payé / Reste à payer à partir des paiements réels,
    et signale dans le chatter les anciens acomptes saisis à la main (à
    ré-encaisser via le bouton « Encaisser » s'ils ont vraiment été perçus)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Reservation = env['hotel.reservation'].with_context(active_test=False)
    reservations = Reservation.search([])
    reservations._compute_payment_amounts()
    reservations.flush_recordset(['deposit_amount', 'amount_paid', 'amount_due'])

    cr.execute("SELECT to_regclass('hotel_legacy_deposit')")
    if not cr.fetchone()[0]:
        return
    cr.execute("SELECT reservation_id, amount FROM hotel_legacy_deposit")
    for res_id, amount in cr.fetchall():
        rec = Reservation.browse(res_id).exists()
        if rec:
            rec.message_post(body=(
                "Ancien acompte saisi à la main : %s %s. L'acompte est "
                "désormais calculé à partir des paiements réels : s'il a bien "
                "été perçu, enregistrez-le avec le bouton « Encaisser »."
            ) % (amount, rec.currency_id.symbol or ''))
    cr.execute("DROP TABLE hotel_legacy_deposit")
