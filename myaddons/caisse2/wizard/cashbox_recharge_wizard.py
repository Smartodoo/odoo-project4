from odoo import models, fields, api, _
class CashboxRechargeWizard(models.TransientModel):
    _name = 'cashbox.recharge.wizard'
    _description = 'Assistant de rechargement de caisse'

    cashbox_id = fields.Many2one('cashbox', string='Caisse', required=True)
    amount = fields.Float(string='Montant à ajouter', required=True)
    note = fields.Text(string='Note (optionnelle)')
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user)
    def action_confirm_recharge(self):
        if self.amount <= 0:
            raise UserError(_("Le montant doit être supérieur à zéro."))

        self.cashbox_id.total_amount += self.amount

        self.env['cashbox.recharge'].create({
            'cashbox_id': self.cashbox_id.id,
            'amount': self.amount,
            'note': self.note,
        })

        return {'type': 'ir.actions.act_window_close'}
