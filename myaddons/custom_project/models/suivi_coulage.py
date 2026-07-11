# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import timedelta


class SuiviCoulage(models.Model):
    """Parent model - Suivi des Coulages (like sale.order)"""
    _name = "suivi.coulage"
    _description = "Suivi des Coulages"
    _order = "name desc, id desc"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Référence', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'))
    project_id = fields.Many2one('custom.project', string='Projet', required=True,
                                  ondelete='cascade', tracking=True,
                                  domain="[('company_id', '=', allowed_company_ids[0])]")

    # Project specific info
    maitre_ouvrage = fields.Char("Maître de l'Ouvrage", tracking=True)
    entreprise_realisation = fields.Char("Entreprise de Réalisation", tracking=True)
    bet_suivi = fields.Char("BET de Suivi", tracking=True)
    responsable_suivi = fields.Char("Responsable Suivi")

    # Lines
    line_ids = fields.One2many('suivi.coulage.line', 'coulage_id', string='Lignes de Coulage', copy=True)

    # Computed fields
    line_count = fields.Integer('Nombre de Coulages', compute='_compute_line_count', store=True)

    # State
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('in_progress', 'En Cours'),
        ('done', 'Terminé'),
    ], string='État', default='draft', tracking=True)

    # Dates
    date_start = fields.Date('Date Début', tracking=True)
    date_end = fields.Date('Date Fin', tracking=True)

    # Notes
    notes = fields.Text('Notes')

    company_id = fields.Many2one('res.company', string='Société',
                                  default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('suivi.coulage') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_in_progress(self):
        self.write({'state': 'in_progress'})

    def action_done(self):
        self.write({'state': 'done'})


class SuiviCoulageLine(models.Model):
    """Child model - Lignes de Coulage (like sale.order.line)"""
    _name = "suivi.coulage.line"
    _description = "Ligne de Suivi Coulage"
    _order = "sequence, id"

    coulage_id = fields.Many2one('suivi.coulage', string='Suivi Coulage',
                                  required=True, ondelete='cascade', index=True)
    project_id = fields.Many2one('custom.project', related='coulage_id.project_id',
                                  store=True, string='Projet')

    # Basic info
    sequence = fields.Integer('N°', default=10)
    name = fields.Char('Désignation des Éléments Coulés', required=True)

    # Bloc info
    bloc = fields.Selection([
        ('bloc_a', 'Bloc A'),
        ('bloc_b', 'Bloc B'),
        ('bloc_ab', 'Bloc A et B'),
    ], string='Bloc')

    # Quantity and concrete plant
    quantite = fields.Float('Quantité (m³)')
    centrale_beton = fields.Char('Centrale à Béton')

    # Pouring date and conditions
    date_coulage = fields.Date('Date de Coulage')
    temperature = fields.Float('Température (C°)')
    heure = fields.Char('Heure')
    nb_eprouvettes = fields.Integer('Nb des Éprouvettes')

    # 7 days test
    date_7_jours = fields.Date('Date après 7 jours', compute='_compute_test_dates', store=True)
    resultat_7_jours = fields.Float('Résultat à 7 jours (MPA)')

    # 28 days test
    date_28_jours = fields.Date('Date à 28 jours', compute='_compute_test_dates', store=True)
    resultat_28_jours = fields.Float('Résultat à 28 jours (MPA)')

    # Additional info
    observation = fields.Text('Observation')
    laboratoire = fields.Char('Laboratoire')

    # State based on test results
    state = fields.Selection([
        ('pending', 'En attente'),
        ('test_7', 'Test 7 jours'),
        ('test_28', 'Test 28 jours'),
        ('done', 'Terminé'),
    ], string='État', compute='_compute_state', store=True)

    # Quality check
    is_conforme_7 = fields.Boolean('Conforme 7j', compute='_compute_conformite', store=True)
    is_conforme_28 = fields.Boolean('Conforme 28j', compute='_compute_conformite', store=True)

    company_id = fields.Many2one('res.company', related='coulage_id.company_id', store=True)

    @api.depends('date_coulage')
    def _compute_test_dates(self):
        for line in self:
            if line.date_coulage:
                line.date_7_jours = line.date_coulage + timedelta(days=7)
                line.date_28_jours = line.date_coulage + timedelta(days=28)
            else:
                line.date_7_jours = False
                line.date_28_jours = False

    @api.depends('resultat_7_jours', 'resultat_28_jours')
    def _compute_state(self):
        for line in self:
            if line.resultat_28_jours:
                line.state = 'done'
            elif line.resultat_7_jours:
                line.state = 'test_7'
            else:
                line.state = 'pending'

    @api.depends('resultat_7_jours', 'resultat_28_jours')
    def _compute_conformite(self):
        """Check if results meet minimum requirements (typically > 20 MPA at 7 days, > 25 MPA at 28 days)"""
        for line in self:
            line.is_conforme_7 = line.resultat_7_jours >= 20.0 if line.resultat_7_jours else False
            line.is_conforme_28 = line.resultat_28_jours >= 25.0 if line.resultat_28_jours else False


class CustomProjectCoulage(models.Model):
    """Extend custom.project to add coulage relation"""
    _inherit = 'custom.project'

    coulage_ids = fields.One2many('suivi.coulage', 'project_id', string='Suivi des Coulages')
    coulage_count = fields.Integer('Nombre de Suivis', compute='_compute_coulage_count')

    @api.depends('coulage_ids')
    def _compute_coulage_count(self):
        for project in self:
            project.coulage_count = len(project.coulage_ids)

    def action_view_coulages(self):
        """Open coulages linked to this project"""
        self.ensure_one()
        action = {
            'name': _('Suivi des Coulages'),
            'type': 'ir.actions.act_window',
            'res_model': 'suivi.coulage',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
            },
        }
        if self.coulage_count == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.coulage_ids.id
        return action
