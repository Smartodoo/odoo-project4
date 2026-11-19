from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """« Carte bancaire » devient « TPE » : renomme les lignes de mode de
    paiement et le journal créés par le module (si leur nom n'a pas été
    personnalisé)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    langs = [code for code, _name in env['res.lang'].get_installed()]
    lines = env['account.payment.method.line'].search([
        ('hotel_payment_mode', '=', 'card')])
    lines.filtered(lambda l: l.name == 'Carte bancaire').write({'name': 'TPE'})
    for journal in lines.journal_id:
        for lang in langs:
            journal_lang = journal.with_context(lang=lang)
            if journal_lang.name == 'Carte bancaire':
                journal_lang.name = 'TPE'
