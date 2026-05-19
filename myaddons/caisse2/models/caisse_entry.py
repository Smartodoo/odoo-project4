from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError

MSG_CAISSE_LECTURE_SEULE = _("Accès refusé: Vous avez uniquement un accès en lecture sur les caisses.")


class CaisseEntry(models.Model):
    _name = "caisse.entry"
    _description = "Encaissement caisse de la société"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = " create_date desc, id desc"

    name = fields.Char(string='Réference', required=True, readonly=True, index=True, copy=False,
                       default='/')

    date = fields.Datetime(string='Date', required=True, default=fields.Datetime.now, tracking=True)
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string="Devise de la société",
    )
    amount = fields.Monetary(string='Montant',
                             required=True, currency_field="company_currency_id", tracking=True)
    amount_paid = fields.Monetary(string='Versement',
                                  currency_field="company_currency_id", tracking=True)
    amount_residual = fields.Monetary(string='Reste à payer',
                                      store=True, currency_field="company_currency_id", tracking=True)
    amount_verse = fields.Monetary(string='Versé', currency_field="company_currency_id", tracking=True)

    description = fields.Text(string='Description', required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'À soumettre'),
        ('approuve', 'Approuvé'),
    ], string='État', default='draft', tracking=True, )

    user_id = fields.Many2one('res.users', 'Caissier', default=lambda self: self.env.user, readonly=True)
    notes = fields.Text(string='Notes Internes', tracking=True)
    company_id = fields.Many2one('res.company', string="Société", default=lambda self: self.env.company,
                                 required=True, index=True, tracking=True)

    cashbox_id = fields.Many2one('cashbox', string='Caisse',
                                 store=True,
                                 tracking=True,
                                 required=True,
                                 readonly=True,
                                 help="Caisse de la société au sein de laquelle cette entrée a été effectuée.")

    sale_order_id = fields.Many2one('sale.order', string='Bon de Commande',
                                    tracking=True, readonly=True)
    client = fields.Many2one(related='sale_order_id.partner_id', string='Client', store=True, readonly=True)
    banque_id = fields.Many2one('res.partner.bank', string="Banque")
    invoice_id = fields.Many2one('account.move', string='Facture', readonly=True)
    payment_id = fields.Many2one('account.payment', string='Paiement', readonly=True)

    @api.model
    def create(self, vals):
        if self.env.user.has_group('caisse2.group_lecture_seule'):
            raise UserError(MSG_CAISSE_LECTURE_SEULE)
        rec = super().create(vals)
        if vals.get('name', '/') in (False, '/', ''):
            vals['name'] = self.env['ir.sequence'].next_by_code('caisse.entry') or '/'
        # 🛡️ Vérifie que l'on modifie bien l'état explicitement
        if 'state' in vals and vals.get('state') == 'approuve':
            if rec.sale_order_id:
                rec.cashbox_id.total_amount += rec.amount_paid
            else:
                rec.cashbox_id.total_amount += rec.amount

        elif 'state' in vals and rec.state == 'approuve' and vals.get('state') == 'draft':
            if rec.sale_order_id:
                rec.cashbox_id.total_amount -= rec.amount_paid
            else:
                rec.cashbox_id.total_amount -= rec.amount

            if not rec.sale_order_id and rec.payment_id:
                rec.payment_id.action_draft()
                rec.payment_id.unlink()

        return rec

    def write(self, vals):
        if self.env.user.has_group('caisse2.group_lecture_seule'):
            raise UserError(MSG_CAISSE_LECTURE_SEULE)
        return super().write(vals)

    def unlink(self):
        if self.env.user.has_group('caisse2.group_lecture_seule'):
            raise UserError(MSG_CAISSE_LECTURE_SEULE)
        for record in self:
            if not record.caisse_entry_id and not record.sales_order_count:
                record.sale_order_id.state_caisse = 'no'
            if record.caisse_entry_id and record.sales_order_count > 1:
                raise UserError(
                    _("Vous ne pouvez pas supprimer cette entrée de caisse.\nIl y a plusieurs encaissements liés à cette entrée de caisse."))
            if record.state != 'draft':
                raise UserError(_("Vous ne pouvez pas supprimer une entrée de caisse approuvée.\n"))
        return super(CaisseEntry, self).unlink()
