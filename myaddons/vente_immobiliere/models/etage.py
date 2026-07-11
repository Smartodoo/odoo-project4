# -*- coding: utf-8 -*-
from odoo import models, fields, api


class VenteEtage(models.Model):
    _name = 'vente.etage'
    _description = 'Étage'
    _order = 'sequence, name'

    name = fields.Char(string='Nom de l\'Étage', required=True)
    sequence = fields.Integer(string='Ordre', default=10)
    bloc_id = fields.Many2one('vente.bloc', string='Bloc', required=True, ondelete='cascade')
    projet_id = fields.Many2one(related='bloc_id.projet_id', string='Projet', store=True, readonly=True)
    appartement_ids = fields.One2many('vente.appartement', 'etage_id', string='Appartements')
    appartement_count = fields.Integer(string='Nombre d\'Appartements',
                                       compute='_compute_appartement_count', store=True)

    @api.depends('appartement_ids')
    def _compute_appartement_count(self):
        for rec in self:
            rec.appartement_count = len(rec.appartement_ids)
