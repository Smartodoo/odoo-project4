from odoo import models, fields, api, _
from odoo.exceptions import UserError

MSG_CAISSE_LECTURE_SEULE = _("Accès refusé: Vous avez uniquement un accès en lecture sur les caisses.")


class CaisseEpenseGlobale(models.Model):
    _name = "caisse.expense.globale"
    _description = "Résumé des dépenses de caisse"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = " create_date desc, id desc"
    _rec_name = 'partner_id'

    # résumé des dépenses de caisse (fournisseur et situation) chaque fournisseur avec son resume et chaque sous traiton avec son résume
    partner_id = fields.Many2one('res.partner', string='Partenaire', tracking=True, required=True)
    partner_type = fields.Selection(string='Type de partenaire', related='partner_id.contact_type', store=True,
                                    tracking=True)
    date_from = fields.Datetime(string='de', required=True, default=fields.Datetime.now, tracking=True)
    date_to = fields.Datetime(string='à', required=True, default=fields.Datetime.now, tracking=True)
    company_id = fields.Many2one('res.company', string="Société", default=lambda self: self.env.company,
                                 required=True, index=True, tracking=True)
    total_expense_amount = fields.Monetary(string='Montant total des dépenses', currency_field="company_currency_id",
                                           compute='_compute_totals',
                                           store=True, tracking=True)
    total_paid_amount = fields.Monetary(string='Montant total versé', currency_field="company_currency_id",
                                        compute='_compute_totals', store=True,
                                        tracking=True)
    total_residual_amount = fields.Monetary(string='Montant total restant', currency_field="company_currency_id",
                                            compute='_compute_totals',
                                            store=True, tracking=True)
    expenses_line_ids = fields.Many2many('caisse.expense', string='Lignes de dépenses',
                                         tracking=True)
    expenses_supplier_line_ids = fields.Many2many('caisse.expense.supplier',
                                                  string='Lignes de dépenses fournisseurs',
                                                  tracking=True)
    project_ids = fields.Many2many('custom.project', string='Projets', compute='_compute_projects', store=True, tracking=True)
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string="Devise de la société",
    )
    user_id = fields.Many2one('res.users', 'Utilisateur', default=lambda self: self.env.user, readonly=True)

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

    @api.depends('expenses_line_ids', 'expenses_supplier_line_ids')
    def _compute_projects(self):
        for record in self:
            project_ids = []
            if record.partner_type == 'SUBCONTRACTOR':
                project_ids = record.expenses_line_ids.mapped('project_id').ids
            elif record.partner_type == 'SUPPLIER':
                project_ids = record.expenses_supplier_line_ids.mapped('project_id').ids
            record.project_ids = [(6, 0, project_ids)]

    @api.depends('expenses_line_ids', 'expenses_supplier_line_ids')
    def _compute_totals(self):
        for record in self:
            total_expense = 0.0
            total_paid = 0.0
            total_residual = 0.0

            if record.partner_type == 'SUBCONTRACTOR':
                for line in record.expenses_line_ids:
                    if line.state == 'approuve':
                        total_expense += line.amount
                        total_paid += line.amount_paid
                        total_residual += line.amount_residual
            elif record.partner_type == 'SUPPLIER':
                for line in record.expenses_supplier_line_ids:
                    if line.state == 'approuve':
                        total_expense += line.amount
                        total_paid += line.amount_paid
                        total_residual += line.amount_residual
            record.total_expense_amount = total_expense
            record.total_paid_amount = total_paid
            record.total_residual_amount = total_residual

    # calculer date_to elle prend tjr la nouvelle date des lignes de dépenses et date_from l'ancienne date des lignes de dépenses
    @api.onchange('expenses_line_ids', 'expenses_supplier_line_ids')
    def _onchange_date_to(self):
        for record in self:
            if record.partner_type == 'SUBCONTRACTOR' and record.expenses_line_ids:
                dates = record.expenses_line_ids.mapped('date')
                record.date_from = min(dates)
                record.date_to = max(dates)
            elif record.partner_type == 'SUPPLIER' and record.expenses_supplier_line_ids:
                dates = record.expenses_supplier_line_ids.mapped('date')
                record.date_from = min(dates)
                record.date_to = max(dates)

    def action_preview_report(self):
        """Prévisualiser le rapport dans un nouvel onglet"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/caisse2.report_caisse_expense_global/%s' % self.id,
            'target': 'new',
        }

    def action_preview_report_multi(self):
        """Prévisualiser le rapport pour plusieurs enregistrements sélectionnés"""
        if not self:
            raise UserError(_("Veuillez sélectionner au moins un enregistrement."))
        ids_str = ','.join(str(rec.id) for rec in self)
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/caisse2.report_caisse_expense_global/%s' % ids_str,
            'target': 'new',
        }
