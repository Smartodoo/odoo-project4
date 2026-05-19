# -*- coding: utf-8 -*-
from odoo import models, fields


class VenteWilaya(models.Model):
    _name = 'vente.wilaya'
    _description = 'Wilaya'
    _order = 'code'

    name = fields.Char(string='Nom', required=True)
    code = fields.Char(string='Code', required=True)
    daira_ids = fields.One2many('vente.daira', 'wilaya_id', string='Dairas')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Le code de la wilaya doit être unique.'),
    ]

    def name_get(self):
        return [(w.id, '%s - %s' % (w.code, w.name)) for w in self]
