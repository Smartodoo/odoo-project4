from odoo import models, fields, api, _
from odoo.exceptions import UserError

MSG_VERSEMENT_LECTURE_SEULE = _("Accès refusé: Vous avez uniquement un accès en lecture sur les versements fournisseurs.")


class DistributionMontant(models.Model):
    _name = 'distribution.montant'
    _description = 'Distribution des motants'

    purchase_id = fields.Many2one('purchase.order', string="Bon d'achat", required=True)
    total = fields.Float(string="Total ", compute="_compute_total", store=True)
    montant = fields.Float(string="Montant", default=0.0)
    versement_id = fields.Many2one('versement.versement', string="Versement", ondelete="cascade")

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user.has_group('Purchase_custom.group_versement_lecture_seule'):
            raise UserError(MSG_VERSEMENT_LECTURE_SEULE)
        return super().create(vals_list)

    def write(self, vals):
        if self.env.user.has_group('Purchase_custom.group_versement_lecture_seule'):
            raise UserError(MSG_VERSEMENT_LECTURE_SEULE)
        return super().write(vals)

    def unlink(self):
        if self.env.user.has_group('Purchase_custom.group_versement_lecture_seule'):
            raise UserError(MSG_VERSEMENT_LECTURE_SEULE)
        return super().unlink()

    @api.depends('purchase_id')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.purchase_id.amount_due_purchase if rec.purchase_id else 0.0
