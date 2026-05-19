from odoo import models, fields, api, _
from odoo.exceptions import UserError


class paiementSituation(models.Model):
    _name = "paiement.situation"
    _description = "Paiement des situations"
    _order = "payment_date desc, id desc"


    situation_id = fields.Many2one("situation", string="Situation", required=True)
    reference = fields.Char("Référence de paiement", required=True)
    partner_id = fields.Many2one("res.partner", string="Sous-traitant", required=True)
    project_id = fields.Many2one("custom.project", string="Projet", required=True,
                                  domain="[('company_id', '=', allowed_company_ids[0])]")
    payment_date = fields.Date("Date de paiement", required=True , default=fields.Date.context_today)
    amount_paid = fields.Float("Montant payé", required=True)
    payment_method_id = fields.Many2one("account.payment.method", string="Méthode de paiement", required=True)
    # caisse = fields.Many2one("cash.box", string="Caisse", required=True)
    note = fields.Text("Notes supplémentaires")
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user, readonly=True)
    company_id = fields.Many2one('res.company', string="Société", default=lambda self: self.env.company, required=True)
    status = fields.Selection([
        ('not_paid', 'Non payé'),
        ('paid', 'Payé'),
    ], string='Statut', default='not_paid')

    # def action_confirm_payment(self):
    #     print("✅ Bouton Confirmer Paiement cliqué :", self.situation_id.name)
    #     self.situation_id.poush_notification()
    #     return {
    #         'effect': {
    #             'fadeout': 'slow',
    #             'message': _('Notification envoyée 🎉'),
    #             'type': 'rainbow_man',
    #         }
    #     }

    def action_validate_payment(self):
        caisse_expense_model = self.env['caisse.expense'].sudo()
        for rec in self:
            associated_payment = caisse_expense_model.search([('situation_id', '=', rec.situation_id.id)], limit=1)
            if associated_payment:
                associated_payment.state = 'approuve'
            rec.sudo().status = 'paid'

    def test_log1(self):
        self.ensure_one()
        print("✅ Bouton Confirmer Paiement cliqué :", self.situation_id.name)
        self.situation_id.poush_notification()
        return {
            'effect': {
                'fadeout': 'slow',
                'message': _('Notification envoyée 🎉'),
                'type': 'rainbow_man',
            }
        }
    # inderdire la suppression des paiements validés
    def unlink(self):
        for rec in self:
            if rec.status == 'paid':
                raise UserError(_("Vous ne pouvez pas supprimer un paiement validé."))
        return super(paiementSituation, self).unlink()