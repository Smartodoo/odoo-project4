# -*- coding: utf-8 -*-
from odoo import models, fields


class VenteDaira(models.Model):
    _name = 'vente.daira'
    _description = 'Daira'
    _order = 'name'

    name = fields.Char(string='Nom', required=True)
    wilaya_id = fields.Many2one('vente.wilaya', string='Wilaya', required=True, ondelete='cascade')
    commune_ids = fields.One2many('vente.commune', 'daira_id', string='Communes')
