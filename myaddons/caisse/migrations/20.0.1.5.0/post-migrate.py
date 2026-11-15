from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Paiements déjà dans une caisse : nature recalculée d'après ce qu'ils
    règlent (un remboursement de note de frais classé à tort en « achat »)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['account.payment'].search([('caisse_session_id', '!=', False)])._caisse_refresh_kind()
