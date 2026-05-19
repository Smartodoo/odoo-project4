from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.osv import expression

MSG_CAISSE_LECTURE_SEULE = _("Accès refusé: Vous avez uniquement un accès en lecture sur les caisses.")


class Cashbox(models.Model):
    _name = 'cashbox'
    _description = 'Gestion des Caisses de la société'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = " create_date desc, id desc"

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Le nom existe déjà !"),
    ]

    active = fields.Boolean(string='Actif', default=True, tracking=True)
    name = fields.Char(string='Nom', required=True, tracking=True, index=True)
    responsible_ids = fields.Many2many('res.users', string='Responsables', required=True,
                                       tracking=True,
                                       help="Les utilisateurs qui sont responsables de cette caisse.")
    notes = fields.Text(string='Notes Internes', tracking=True)
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string="Devise de la société",
    )
    total_amount = fields.Monetary(string='Montant Total', currency_field="company_currency_id")
    company_id = fields.Many2one('res.company', string="Société", default=lambda self: self.env.company,
                                 required=True, index=True, tracking=True, )
    entry_ids = fields.One2many('caisse.entry', 'cashbox_id', string='Encaissements')
    entry_count = fields.Integer(compute='_compute_entry_count', string='Nombre d\'encaissements', store='True')

    supplier_ids = fields.One2many('caisse.expense.supplier', 'cashbox_id', string='Fournisseurs')
    supplier_count = fields.Integer(compute='_compute_supplier_count', store='True', string='Nombre de fournisseurs')

    transfer_ids = fields.One2many('cashbox.transfer', 'source_cashbox_id', string='Transfers')
    transfer_count = fields.Integer(compute='_compute_transfer_count', store='True', string='Nombre de transferts')

    expense_ids = fields.One2many('caisse.expense', 'cashbox_id', string='Paiements Situations')
    expense_count = fields.Integer(compute='_compute_caisse_expense_count', store='True',
                                   string='Nombre de paiements situations')

    journal_id = fields.Many2one('account.journal', string='Journal', tracking=True, compute='_get_journal_id_value',
                                 store=True)
    recharge_ids = fields.One2many('cashbox.recharge', 'cashbox_id', string="Rechargements")
    recharge_count = fields.Integer(string="Nb Rechargements", compute="_compute_recharge_count")
    access_users = fields.Many2many('res.users', 'cashbox_user_table', string='Utilisateurs accessibles')

    @api.depends('entry_ids')
    def _compute_entry_count(self):
        for rec in self:
            related_entry_ids = self.env['caisse.entry'].search([('cashbox_id', '=', rec.id)])
            rec.entry_count = len(related_entry_ids)

    @api.depends('supplier_ids')
    def _compute_supplier_count(self):
        for rec in self:
            related_supplier_ids = self.env['caisse.expense.supplier'].search([('cashbox_id', '=', rec.id)])
            rec.supplier_count = len(related_supplier_ids)

    @api.depends('transfer_ids')
    def _compute_transfer_count(self):
        for rec in self:
            related_transfer_ids = self.env['cashbox.transfer'].search([('source_cashbox_id', '=', rec.id)])
            rec.transfer_count = len(related_transfer_ids)

    @api.depends('recharge_ids')
    def _compute_recharge_count(self):
        for record in self:
            record.recharge_count = len(record.recharge_ids)

    @api.depends('expense_ids')
    def _compute_caisse_expense_count(self):
        for rec in self:
            related_expense_ids = self.env['caisse.expense'].search([('cashbox_id', '=', rec.id)])
            rec.expense_count = len(related_expense_ids)

    def _get_journal_id_value(self):
        for rec in self:
            rec.journal_id = self.env['account.journal'].search([('id', '=', '7')]).id

    def action_view_recharge_ids(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rechargements de Caisse'),
            'res_model': 'cashbox.recharge',
            'view_mode': 'tree,form',
            'domain': [('cashbox_id', '=', self.id)],
            'context': {'default_cashbox_id': self.id}
        }

    def action_view_supplier_ids(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'caisse2.caisse_expense_supplier_act_window')
        result = action
        result['context'] = {'default_cashbox_id': self.id,
                             }
        result['domain'] = [('cashbox_id', '=', self.id)]
        return result

    def action_view_entry_ids(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'caisse2.caisse_entry_act_window')
        result = action
        result['context'] = {'default_cashbox_id': self.id,
                             }
        result['domain'] = [('cashbox_id', '=', self.id)]
        return result

    def action_view_transfer_ids(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'caisse2.cashbox_transfer_act_window')
        result = action
        result['context'] = {'default_source_cashbox_id': self.id,
                             }
        result['domain'] = [('source_cashbox_id', '=', self.id)]
        return result

    def action_view_caisse_expense_ids(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'caisse2.caisse_expense_act_window')
        result = action
        result['context'] = {'default_cashbox_id': self.id,
                             }
        result['domain'] = [('cashbox_id', '=', self.id)]
        return result

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
        for record in self:
            if record.entry_ids or record.transfer_ids or record.supplier_ids or record.expense_ids:
                raise UserError(
                    _("Impossible de supprimer cette caisse : des transactions y sont associées.") % record.name)

        return super(Cashbox, self).unlink()

    def action_recharge_cashbox(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Enrichir la caisse'),
            'res_model': 'cashbox.recharge.wizard',
            'view_mode': 'form',
            'context': {('default_cashbox_id', self.id)},
            'target': 'new',
            'context': {'default_cashbox_id': self.id}
        }

    def action_archive(self):
        for record in self:
            if record.total_amount != 0:
                raise UserError(
                    _("Impossible d'archiver cette caisse : le solde doit être nul.\nSolde actuel : %.2f %s") %
                    (record.total_amount, record.company_currency_id.symbol))
        return super(Cashbox, self).action_archive()

    def action_unarchive(self):
        return super(Cashbox, self).action_unarchive()
