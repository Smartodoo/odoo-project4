# -*- coding: utf-8 -*-
from odoo import models, fields, api


class VenteProjet(models.Model):
    _name = 'vente.projet'
    _description = 'Projet Immobilier'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # ── 1. Informations Générales ──
    project_id = fields.Many2one('custom.project', string='Projet BTP', tracking=True)
    name = fields.Char(string='Intitulé Administratif', required=True, tracking=True)
    code = fields.Char(string='Code', tracking=True)
    reference = fields.Char(string='Référence', readonly=True, copy=False, default='/')
    type = fields.Selection([
        ('vente', 'Vente'),
        ('location', 'Location'),
    ], string='Type', required=True, default='vente', tracking=True)
    avancement = fields.Float(string='Avancement (%)', tracking=True)
    date_start = fields.Date(string='Date Début', tracking=True)
    duree = fields.Integer(string='Durée (mois)')
    date_achevement = fields.Date(string="Date d'Achèvement", tracking=True)
    description = fields.Html(string='Description')

    # ── 2. Localisation ──
    country_id = fields.Many2one('res.country', string='Pays', tracking=True)
    wilaya_id = fields.Many2one('vente.wilaya', string='Wilaya', tracking=True)
    lieu_dit = fields.Char(string='Lieu-dit / Quartier / Cité')
    repere = fields.Char(string='Repère')
    address = fields.Char(string='Adresse')
    superficie_terrain = fields.Float(string='Superf. Terrain (m²)')

    # ── 3-1. Identification Juridique et Technique ──
    conservation_fonciere = fields.Char(string='Conservation Foncière de')
    livret_foncier = fields.Char(string='Livret Foncier')
    delivre_le = fields.Date(string='Délivré le')
    delivre_par = fields.Char(string='Délivré par')

    # 3-1-1. Acte Notarié
    acte_num_enregistrement = fields.Char(string="N° d'Enregistrement de l'Acte")
    acte_date_publication = fields.Date(string='Date de Publication (Acte)')
    acte_volume = fields.Char(string='Volume (Acte)')
    acte_folio = fields.Char(string='Folio (Acte)')

    # 3-1-2. État Descriptif de Division
    edd_num_enregistrement = fields.Char(string="N° d'Enregistrement de l'EDD")
    edd_date_publication = fields.Date(string='Date de Publication (EDD)')
    edd_volume = fields.Char(string='Volume (EDD)')
    edd_folio = fields.Char(string='Folio (EDD)')
    reference_cadastrale = fields.Char(string='Référence Cadastrale')

    # ── 3-2. Permis et Certificats ──
    permis_lotir_num = fields.Char(string='Permis de Lotir N°')
    permis_lotir_date = fields.Date(string='Permis de Lotir du')
    permis_lotir_par = fields.Char(string='Permis de Lotir par')

    certificat_amenagement_num = fields.Char(string='Certificat Aménagement N°')
    certificat_amenagement_date = fields.Date(string='Certificat Aménagement du')
    certificat_amenagement_par = fields.Char(string='Certificat Aménagement par')

    permis_construire_num = fields.Char(string='Permis de Construire N°')
    permis_construire_date = fields.Date(string='Permis de Construire du')
    permis_construire_par = fields.Char(string='Permis de Construire par')

    # ── 4. Structure ──
    bloc_ids = fields.One2many('vente.bloc', 'projet_id', string='Blocs')
    bloc_count = fields.Integer(string='Nombre de Blocs', compute='_compute_bloc_count', store=True)
    appartement_count = fields.Integer(string="Nombre d'Appartements",
                                       compute='_compute_appartement_count', store=True)
    reservation_count = fields.Integer(string='Nombre de Réservations',
                                       compute='_compute_reservation_count')

    # ── Divers ──
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('in_progress', 'En Cours'),
        ('done', 'Terminé'),
    ], string='État', default='draft', tracking=True)
    company_id = fields.Many2one('res.company', string='Société',
                                 default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one('res.currency', string='Devise',
                                  related='company_id.currency_id', store=True)

    @api.depends('bloc_ids')
    def _compute_bloc_count(self):
        for rec in self:
            rec.bloc_count = len(rec.bloc_ids)

    @api.depends('bloc_ids.appartement_count')
    def _compute_appartement_count(self):
        for rec in self:
            rec.appartement_count = sum(bloc.appartement_count for bloc in rec.bloc_ids)

    def _compute_reservation_count(self):
        for rec in self:
            rec.reservation_count = self.env['vente.reservation'].search_count(
                [('projet_id', '=', rec.id)])

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', '/') in (False, '/', ''):
                vals['reference'] = self.env['ir.sequence'].next_by_code('vente.projet') or '/'
        return super().create(vals_list)

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_view_blocs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Blocs',
            'res_model': 'vente.bloc',
            'view_mode': 'tree,form',
            'domain': [('projet_id', '=', self.id)],
            'context': {'default_projet_id': self.id},
        }

    def action_view_appartements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Appartements',
            'res_model': 'vente.appartement',
            'view_mode': 'tree,form',
            'domain': [('projet_id', '=', self.id)],
        }

    def action_view_reservations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Réservations',
            'res_model': 'vente.reservation',
            'view_mode': 'tree,form',
            'domain': [('projet_id', '=', self.id)],
        }
