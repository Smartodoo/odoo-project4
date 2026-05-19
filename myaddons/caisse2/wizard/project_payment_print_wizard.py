# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ProjectPaymentPrintWizard(models.TransientModel):
    _name = 'project.payment.print.wizard'
    _description = 'Wizard pour impression des paiements par projet'

    project_recap_id = fields.Many2one('caisse.expense.project', string='Récap Projet', required=True)
    project_id = fields.Many2one('custom.project', string='Projet', related='project_recap_id.project_id', readonly=True)
    date_from = fields.Date(string='Date début', required=True)
    date_to = fields.Date(string='Date fin', required=True)
    payment_type = fields.Selection([
        ('all', 'Tous les paiements'),
        ('supplier', 'Fournisseurs uniquement'),
        ('situation', 'Situations uniquement')
    ], string='Type de paiement', default='all', required=True)

    company_id = fields.Many2one('res.company', related='project_recap_id.company_id', readonly=True)
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise UserError(_("La date de début doit être antérieure à la date de fin."))

    supplier_payment_ids = fields.Many2many('caisse.expense.supplier', string='Paiements Fournisseurs', compute='_compute_payments', store=False)
    situation_payment_ids = fields.Many2many('caisse.expense', string='Paiements Situations', compute='_compute_payments', store=False)

    @api.depends('project_id', 'date_from', 'date_to', 'payment_type')
    def _compute_payments(self):
        for record in self:
            supplier_payments = self.env['caisse.expense.supplier']
            situation_payments = self.env['caisse.expense']

            if record.project_id and record.date_from and record.date_to:
                if record.payment_type in ['all', 'supplier']:
                    supplier_payments = self.env['caisse.expense.supplier'].search([
                        ('project_id', '=', record.project_id.id),
                        ('date', '>=', record.date_from),
                        ('date', '<=', record.date_to),
                        ('state', '=', 'approuve')
                    ])

                if record.payment_type in ['all', 'situation']:
                    situation_payments = self.env['caisse.expense'].search([
                        ('project_id', '=', record.project_id.id),
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
        return self.env.ref('caisse2.action_report_project_payments').report_action(self)

    def action_preview_report(self):
        """Prévisualiser le rapport dans un nouvel onglet"""
        self.ensure_one()

        # Vérifier qu'il y a des paiements
        if not self.supplier_payment_ids and not self.situation_payment_ids:
            raise UserError(_("Aucun paiement trouvé pour les critères sélectionnés."))

        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/caisse2.report_project_payments_template/%s' % self.id,
            'target': 'new',
        }
