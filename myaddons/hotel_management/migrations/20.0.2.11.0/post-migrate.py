from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Réservations existantes : une fiche par adulte (hors client) et par enfant."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['hotel.reservation'].with_context(active_test=False).search([])._sync_guests()
