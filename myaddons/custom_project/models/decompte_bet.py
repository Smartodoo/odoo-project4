# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class DecompteBet(models.Model):
    """Parent model - Décompte BET"""
    _name = "decompte.bet"
    _description = "Décompte BET"
    _order = "name desc, id desc"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Référence', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'))
    project_id = fields.Many2one('custom.project', string='Projet', required=True,
                                  ondelete='cascade', tracking=True,
                                  domain="[('company_id', '=', allowed_company_ids[0])]")

    # Decompte info
    numero_decompte = fields.Char("Numéro Décompte", tracking=True)
    date_decompte = fields.Date("Date Décompte", tracking=True)

    # BET info
    bet_name = fields.Char("BET", tracking=True)
    bet_address = fields.Char("Adresse BET")
    bet_responsable = fields.Char("Responsable BET")

    # Project info
    projet_designation = fields.Char("Désignation Projet")
    projet_wilaya = fields.Char("Wilaya")

    # Contractor info
    entreprise = fields.Char("Entreprise")

    # Lines
    line_ids = fields.One2many('decompte.bet.line', 'decompte_id', string='Lignes', copy=True)

    # Computed totals
    montant_total_precedent = fields.Float('Total Précédent', compute='_compute_totals', store=True)
    montant_total_mois = fields.Float('Total Mois', compute='_compute_totals', store=True)
    montant_total_cumule = fields.Float('Total Cumulé', compute='_compute_totals', store=True)

    line_count = fields.Integer('Nombre de Lignes', compute='_compute_line_count', store=True)

    # State
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('validated', 'Validé'),
        ('paid', 'Payé'),
    ], string='État', default='draft', tracking=True)

    # Amount in words
    montant_en_lettres = fields.Text("Montant en Lettres")

    # Notes
    notes = fields.Text('Notes')

    company_id = fields.Many2one('res.company', string='Société',
                                  default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('decompte.bet') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids', 'line_ids.montant_precedent', 'line_ids.montant_mois', 'line_ids.montant_cumule')
    def _compute_totals(self):
        for record in self:
            record.montant_total_precedent = sum(record.line_ids.mapped('montant_precedent'))
            record.montant_total_mois = sum(record.line_ids.mapped('montant_mois'))
            record.montant_total_cumule = sum(record.line_ids.mapped('montant_cumule'))

    @api.depends('line_ids')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_validate(self):
        self.write({'state': 'validated'})

    def action_paid(self):
        self.write({'state': 'paid'})


class DecompteBetLine(models.Model):
    """Child model - Lignes de Décompte BET"""
    _name = "decompte.bet.line"
    _description = "Ligne de Décompte BET"
    _order = "sequence, id"

    decompte_id = fields.Many2one('decompte.bet', string='Décompte',
                                   required=True, ondelete='cascade', index=True)
    project_id = fields.Many2one('custom.project', related='decompte_id.project_id',
                                  store=True, string='Projet')

    # Basic info
    sequence = fields.Integer('N°', default=10)
    name = fields.Char('Désignation', required=True)
    date = fields.Date('Date')

    # Quantities
    quantite_precedent = fields.Float('Qté Précédent', digits=(16, 2))
    quantite_mois = fields.Float('Qté Mois', digits=(16, 2))
    quantite_cumule = fields.Float('Qté Cumulé', compute='_compute_quantite_cumule', store=True)

    # Price
    prix_unitaire = fields.Float('Prix Unitaire', digits=(16, 2))

    # Amounts
    montant_precedent = fields.Float('Montant Précédent', compute='_compute_montants', store=True)
    montant_mois = fields.Float('Montant Mois', compute='_compute_montants', store=True)
    montant_cumule = fields.Float('Montant Cumulé', compute='_compute_montants', store=True)

    # Additional info
    observation = fields.Text('Observation')
    is_subtotal = fields.Boolean('Sous-total', default=False)

    company_id = fields.Many2one('res.company', related='decompte_id.company_id', store=True)

    @api.depends('quantite_precedent', 'quantite_mois')
    def _compute_quantite_cumule(self):
        for line in self:
            line.quantite_cumule = line.quantite_precedent + line.quantite_mois

    @api.depends('quantite_precedent', 'quantite_mois', 'quantite_cumule', 'prix_unitaire')
    def _compute_montants(self):
        for line in self:
            line.montant_precedent = line.quantite_precedent * line.prix_unitaire
            line.montant_mois = line.quantite_mois * line.prix_unitaire
            line.montant_cumule = line.quantite_cumule * line.prix_unitaire


class CustomProjectDecompte(models.Model):
    """Extend custom.project to add decompte relation"""
    _inherit = 'custom.project'

    decompte_ids = fields.One2many('decompte.bet', 'project_id', string='Décomptes BET')
    decompte_count = fields.Integer('Nombre de Décomptes', compute='_compute_decompte_count')

    @api.depends('decompte_ids')
    def _compute_decompte_count(self):
        for project in self:
            project.decompte_count = len(project.decompte_ids)

    def action_view_decomptes(self):
        """Open decomptes linked to this project"""
        self.ensure_one()
        action = {
            'name': _('Décomptes BET'),
            'type': 'ir.actions.act_window',
            'res_model': 'decompte.bet',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
            },
        }
        if self.decompte_count == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.decompte_ids.id
        return action