# -*- coding: utf-8 -*-
from odoo import models, fields


class VenteCommune(models.Model):
    _name = 'vente.commune'
    _description = 'Commune'
    _order = 'name'

    name = fields.Char(string='Nom', required=True)
    daira_id = fields.Many2one('vente.daira', string='Daira', required=True, ondelete='cascade')
