# -*- coding: utf-8 -*-
from odoo import models, fields, api


class VenteBloc(models.Model):
    _name = 'vente.bloc'
    _description = 'Bloc'
    _order = 'name'

    name = fields.Char(string='Code / N°', required=True)
    projet_id = fields.Many2one('vente.projet', string='Projet', required=True, ondelete='cascade')
    nbre_etage = fields.Integer(string="Nbre d'Étages")
    mezzanine = fields.Boolean(string='Mezzanine')
    nbre_entre_sols = fields.Integer(string="Nbre d'Entre-sols")
    nbre_sous_sols = fields.Integer(string='Nbre de Sous-sols')

    etage_ids = fields.One2many('vente.etage', 'bloc_id', string='Étages')
    etage_count = fields.Integer(string="Nbre d'Étages (réels)", compute='_compute_etage_count', store=True)
    appartement_count = fields.Integer(string="Nombre d'Appartements",
                                       compute='_compute_appartement_count', store=True)

    @api.depends('etage_ids')
    def _compute_etage_count(self):
        for rec in self:
            rec.etage_count = len(rec.etage_ids)

    @api.depends('etage_ids.appartement_count')
    def _compute_appartement_count(self):
        for rec in self:
            rec.appartement_count = sum(etage.appartement_count for etage in rec.etage_ids)
