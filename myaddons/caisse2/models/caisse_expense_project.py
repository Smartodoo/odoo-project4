from odoo import models, fields, api, _
from odoo.exceptions import UserError

MSG_CAISSE_LECTURE_SEULE = _("Accès refusé: Vous avez uniquement un accès en lecture sur les caisses.")


class CaisseExpenseProject(models.Model):
    _name = "caisse.expense.project"
    _description = "Récapitulatif des dépenses de caisse par projet"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "create_date desc, id desc"
    _rec_name = 'project_id'

    project_id = fields.Many2one('custom.project', string='Projet', tracking=True, required=True)
    date_from = fields.Datetime(string='Date début', required=True, default=fields.Datetime.now, tracking=True)
    date_to = fields.Datetime(string='Date fin', required=True, default=fields.Datetime.now, tracking=True)
    company_id = fields.Many2one('res.company', string="Société", default=lambda self: self.env.company,
                                 required=True, index=True, tracking=True)

    # Montants totaux
    total_expense_amount = fields.Monetary(
        string='Montant total des dépenses',
        currency_field="company_currency_id",
        compute='_compute_totals',
        store=True,
        tracking=True
    )
    total_paid_amount = fields.Monetary(
        string='Montant total versé',
        currency_field="company_currency_id",
        compute='_compute_totals',
        store=True,
        tracking=True
    )
    total_residual_amount = fields.Monetary(
        string='Montant total restant',
        currency_field="company_currency_id",
        compute='_compute_totals',
        store=True,
        tracking=True
    )

    # Montants par catégorie
    total_situation_amount = fields.Monetary(
        string='Total Paiements Situations',
        currency_field="company_currency_id",
        compute='_compute_totals',
        store=True
    )
    total_supplier_amount = fields.Monetary(
        string='Total Paiements Fournisseurs',
        currency_field="company_currency_id",
        compute='_compute_totals',
        store=True
    )

    # Lignes de dépenses
    expenses_line_ids = fields.Many2many(
        'caisse.expense',
        string='Paiements Situations',
        tracking=True
    )
    expenses_supplier_line_ids = fields.Many2many(
        'caisse.expense.supplier',
        string='Paiements Fournisseurs',
        tracking=True
    )

    # Partenaires impliqués
    partner_ids = fields.Many2many(
        'res.partner',
        string='Partenaires',
        compute='_compute_partners',
        store=True
    )

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
    def _compute_partners(self):
        """Calcule la liste des partenaires impliqués dans le projet"""
        for record in self:
            partner_ids = []

            # Partenaires des situations (sous-traitants)
            if record.expenses_line_ids:
                situation_partners = record.expenses_line_ids.mapped('situation_id.original_subcontractor_id')
                partner_ids.extend(situation_partners.ids)

            # Partenaires des fournisseurs
            if record.expenses_supplier_line_ids:
                supplier_partners = record.expenses_supplier_line_ids.mapped('fournisseur')
                partner_ids.extend(supplier_partners.ids)

            record.partner_ids = [(6, 0, list(set(partner_ids)))]

    @api.depends('expenses_line_ids', 'expenses_supplier_line_ids')
    def _compute_totals(self):
        """Calcule les totaux des dépenses par projet"""
        for record in self:
            total_expense = 0.0
            total_paid = 0.0
            total_residual = 0.0
            total_situation = 0.0
            total_supplier = 0.0

            # Calcul pour les paiements situations
            for line in record.expenses_line_ids:
                if line.state == 'approuve':
                    total_expense += line.amount
                    total_paid += line.amount_paid
                    total_residual += line.amount_residual
                    total_situation += line.amount

            # Calcul pour les paiements fournisseurs
            for line in record.expenses_supplier_line_ids:
                if line.state == 'approuve':
                    total_expense += line.amount
                    total_paid += line.amount_paid
                    total_residual += line.amount_residual
                    total_supplier += line.amount

            record.total_expense_amount = total_expense
            record.total_paid_amount = total_paid
            record.total_residual_amount = total_residual
            record.total_situation_amount = total_situation
            record.total_supplier_amount = total_supplier

    @api.onchange('expenses_line_ids', 'expenses_supplier_line_ids')
    def _onchange_date_to(self):
        """Calcule automatiquement les dates de début et fin basées sur les lignes"""
        for record in self:
            dates = []

            if record.expenses_line_ids:
                dates.extend(record.expenses_line_ids.mapped('date'))

            if record.expenses_supplier_line_ids:
                dates.extend(record.expenses_supplier_line_ids.mapped('date'))

            if dates:
                record.date_from = min(dates)
                record.date_to = max(dates)

    def action_preview_report(self):
        """Prévisualiser le rapport dans un nouvel onglet"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/caisse2.report_caisse_expense_project_template/%s' % self.id,
            'target': 'new',
        }

    def action_preview_report_multi(self):
        """Prévisualiser le rapport pour plusieurs enregistrements sélectionnés"""
        if not self:
            raise UserError(_("Veuillez sélectionner au moins un enregistrement."))
        ids_str = ','.join(str(rec.id) for rec in self)
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/caisse2.report_caisse_expense_project_template/%s' % ids_str,
            'target': 'new',
        }
