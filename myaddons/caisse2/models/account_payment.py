from odoo import models, fields, api, _


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    cashbox_id = fields.Many2one('cashbox', string='Caisse', tracking=True, compute='get_cashbox_id_by_default',
                                 store=True)

    @api.depends()
    def _compute_is_admin(self):
        for rec in self:
            rec.is_user_admin = self.env.user.has_group('base.group_system')

    @api.depends()
    def get_cashbox_id_by_default(self):
        """Retourne la caisse par défaut de l'utilisateur connecté"""
        # Vérifie si l'utilisateur est un administrateur on retourne tous les caisses
        if self.env.user.has_group('base.group_system'):
            cashbox = self.env['cashbox'].search([('id', '=', 3)], limit=1)
        # Sinon, on retourne la caisse associée à l'utilisateur
        # (s'il y en a une)
        else:
            user = self.env.user
            cashbox = self.env['cashbox'].search([('responsible_ids', '=', user.id)], limit=1)
        return cashbox.id if cashbox else False

    @api.model
    def create(self, vals):
        # 1) debug incoming values
        print("AccountPayment.create called with vals: %s", vals)

        # 2) actually create the payment record
        rec = super(AccountPayment, self).create(vals)
        print(" → new payment id=%s, cashbox=%s, sale=%s, purchase=%s",
              rec.id, rec.cashbox_id, rec.sale_order_id, rec.purchase_order_id)

        # 3) if there's a cashbox set, create your caisse records
        if rec.cashbox_id:
            # sale.order case
            if rec.sale_order_id:
                paid_before = sum(p.amount for p in rec.sale_order_id.payment_ids if p.id != rec.id)
                amount_verse = paid_before + rec.amount
                self.env['caisse.entry'].sudo().create({
                    'name': self.env['ir.sequence'].next_by_code('caisse.entry') or '/',
                    'sale_order_id': rec.sale_order_id.id,
                    'amount': rec.sale_order_id.amount_total,
                    'amount_paid': rec.amount,
                    'amount_verse': amount_verse,
                    'amount_residual': rec.sale_order_id.amount_total - amount_verse,
                    'description': _(f"Paiement de commande {rec.sale_order_id.name}"),
                    'company_id': rec.company_id.id,
                    'user_id': self.env.uid,
                    'cashbox_id': rec.cashbox_id.id,
                    'state': 'approuve',
                })
                print("  → created caisse.entry for sale %s", rec.sale_order_id.name)

            # purchase.order case
            if rec.purchase_order_id:
                paid_before = sum(p.amount for p in rec.purchase_order_id.payment_purchase_ids if p.id != rec.id)
                amount_verse = paid_before + rec.amount
                self.env['caisse.expense.supplier'].sudo().create({
                    'name': self.env['ir.sequence'].next_by_code('caisse.expense.supplier') or '/',
                    'purchase_id': rec.purchase_order_id.id,
                    'amount': rec.purchase_order_id.amount_total,
                    'amount_paid': rec.amount,
                    'amount_verse': amount_verse,
                    'amount_residual': rec.purchase_order_id.amount_total - amount_verse,
                    'description': _(f"Paiement de bon d'achat {rec.purchase_order_id.name}"),
                    'company_id': rec.company_id.id,
                    'user_id': self.env.uid,
                    'cashbox_id': rec.cashbox_id.id,
                    'state': 'draft',
                })
                print("  → created caisse.expense.supplier for purchase %s", rec.purchase_order_id.name)

        # 4) return the newly created record
        return rec


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    cashbox_id = fields.Many2one('cashbox', string='Caisse', required=True, compute='get_cashbox_id_by_default',
                                 store=True)
    is_user_admin = fields.Boolean(compute="_compute_is_admin", store=False)

    def _compute_is_admin(self):
        for rec in self:
            rec.is_user_admin = self.env.user.has_group('base.group_system')

    def get_cashbox_id_by_default(self):
        """Retourne la caisse par défaut de l'utilisateur connecté"""
        # Vérifie si l'utilisateur est un administrateur on retourne tous les caisses
        if self.env.user.has_group('base.group_system'):
            cashbox = self.env['cashbox'].search([('name', '=', 'Caisse Principale')], limit=1)
        # Sinon, on retourne la caisse associée à l'utilisateur
        # (s'il y en a une)
        else:
            user = self.env.user
            cashbox = self.env['cashbox'].search([('responsible_ids', '=', user.id)], limit=1)
        return cashbox.id if cashbox else False

    def action_create_payments(self):
        payments = self._create_payments()

        # Transfert du champ cashbox_id vers chaque payment
        for wizard in self:
            for payment in payments:
                payment.cashbox_id = wizard.cashbox_id.id
                print('wizard_cashbox_id:', wizard.cashbox_id.id)

        # Code d'origine conservé
        if self._context.get('dont_redirect_to_payments'):
            return True

        action = {
            'name': _('Payments'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'context': {'create': False},
        }
        if len(payments) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': payments.id,
            })
        else:
            action.update({
                'view_mode': 'tree,form',
                'domain': [('id', 'in', payments.ids)],
            })
        return action
