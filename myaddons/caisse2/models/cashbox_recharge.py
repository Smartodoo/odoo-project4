from odoo import models, fields, api, _
from odoo.exceptions import UserError

MSG_CAISSE_LECTURE_SEULE = _("Accès refusé: Vous avez uniquement un accès en lecture sur les caisses.")


class CashboxRecharge(models.Model):
    _name = 'cashbox.recharge'
    _description = 'Rechargement de Caisse'

    cashbox_id = fields.Many2one('cashbox', string='Caisse', required=True)
    date = fields.Datetime(string='Date', default=fields.Datetime.now, readonly=True)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user, readonly=True)
    note = fields.Text(string='Note')
    amount = fields.Monetary(string='Montant ajouté',currency_field="company_currency_id", required=True)
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string="Devise de la société",
    )
    company_id = fields.Many2one('res.company', string="Société", default=lambda self: self.env.company,
                                 required=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user.has_group('caisse2.group_lecture_seule'):
            raise UserError(MSG_CAISSE_LECTURE_SEULE)
        return super().create(vals_list)

    def write(self, vals):
        if self.env.user.has_group('caisse2.group_lecture_seule'):
            raise UserError(MSG_CAISSE_LECTURE_SEULE)
        return super().write(vals)

    def unlink(self):
        if self.env.user.has_group('caisse2.group_lecture_seule'):
            raise UserError(MSG_CAISSE_LECTURE_SEULE)
        return super().unlink()

    def action_preview_report(self):
        """Prévisualiser le rapport dans un nouvel onglet"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/caisse2.report_cashbox_recharge_template/%s' % self.id,
            'target': 'new',
        }