# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class GlobalExpensePrintWizard(models.TransientModel):
    _name = 'global.expense.print.wizard'
    _description = 'Wizard pour impression des paiements de dépenses globales'

    global_expense_id = fields.Many2one('caisse.expense.globale', string='Dépense Globale', required=True)
    date_from = fields.Date(string='Date début', required=True)
    date_to = fields.Date(string='Date fin', required=True)

    # Info du partenaire (fournisseur ou sous-traitant)
    partner_id = fields.Many2one('res.partner', string='Partenaire', compute='_compute_partner_info', readonly=True, store=False)
    partner_type = fields.Selection([('SUPPLIER', 'Fournisseur'), ('SUBCONTRACTOR', 'Sous-traitant')],
                                     string='Type', compute='_compute_partner_info', readonly=True, store=False)

    company_id = fields.Many2one('res.company', compute='_compute_partner_info', readonly=True, store=False)
    company_currency_id = fields.Many2one('res.currency', compute='_compute_partner_info', readonly=True, store=False)

    # Paiements calculés
    supplier_payment_ids = fields.Many2many('caisse.expense.supplier', string='Paiements Fournisseurs', compute='_compute_payments', store=False)
    situation_payment_ids = fields.Many2many('caisse.expense', string='Paiements Situations', compute='_compute_payments', store=False)

    @api.depends('global_expense_id')
    def _compute_partner_info(self):
        for record in self:
            if record.global_expense_id:
                record.partner_id = record.global_expense_id.partner_id
                record.partner_type = record.global_expense_id.partner_type
                record.company_id = record.global_expense_id.company_id
                record.company_currency_id = record.global_expense_id.company_currency_id
            else:
                record.partner_id = False
                record.partner_type = False
                record.company_id = False
                record.company_currency_id = False

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise UserError(_("La date de début doit être antérieure à la date de fin."))

    @api.depends('partner_id', 'partner_type', 'date_from', 'date_to')
    def _compute_payments(self):
        for record in self:
            supplier_payments = self.env['caisse.expense.supplier']
            situation_payments = self.env['caisse.expense']

            if record.partner_id and record.date_from and record.date_to:
                if record.partner_type == 'SUPPLIER':
                    # Chercher les paiements fournisseurs
                    supplier_payments = self.env['caisse.expense.supplier'].search([
                        ('fournisseur', '=', record.partner_id.id),
                        ('date', '>=', record.date_from),
                        ('date', '<=', record.date_to),
                        ('state', '=', 'approuve')
                    ])
                elif record.partner_type == 'SUBCONTRACTOR':
                    # Chercher les paiements situations
                    situation_payments = self.env['caisse.expense'].search([
                        ('situation_id.original_subcontractor_id', '=', record.partner_id.id),
                        ('date', '>=', record.date_from),
                        ('date', '<=', record.date_to),
                        ('state', '=', 'approuve')
                    ])

            record.supplier_payment_ids = supplier_payments
            record.situation_payment_ids = situation_payments

    def action_print_report(self):
        self.ensure_one()

        # Vérifier qu'il y a des paiements
        if not self.supplier_payment_ids and not self.situation_payment_ids:
            raise UserError(_("Aucun paiement trouvé pour les critères sélectionnés."))

        # Retourner l'action pour générer le PDF
        return self.env.ref('caisse2.action_report_global_expense_payments').report_action(self)

    def action_preview_report(self):
        """Prévisualiser le rapport dans un nouvel onglet"""
        self.ensure_one()

        # Vérifier qu'il y a des paiements
        if not self.supplier_payment_ids and not self.situation_payment_ids:
            raise UserError(_("Aucun paiement trouvé pour les critères sélectionnés."))

        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/caisse2.report_global_expense_payments_template/%s' % self.id,
            'target': 'new',
        }
