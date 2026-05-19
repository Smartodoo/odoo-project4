from odoo import api, SUPERUSER_ID
from odoo.addons.payment_cheque_ref.hooks import sync_cheque_ref_method_lines


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    sync_cheque_ref_method_lines(env)
