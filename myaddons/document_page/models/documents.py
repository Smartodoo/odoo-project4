# -*- coding: utf-8 -*-
from odoo import api, fields, models
from datetime import datetime


class DocumentDocument(models.Model):
    _name = 'document.document'
    _description = 'Document (dossier / fichier)'
    _order = 'name'

    name = fields.Char(string='Nom', required=True)
    dossier_id = fields.Many2one('document.document', string='Dossier ', ondelete='cascade')
    detenteur_id = fields.Many2one('res.users', string="Détenteur", default=lambda self: self.env.uid, readonly=True)
    mise_a_jour = fields.Datetime(string='Mise à jour le', default=fields.Datetime.now,
                                  help='Date et heure de la dernière modification', readonly=True)
    taille_de_fichier = fields.Integer(string='Taille (octets)', help='Taille du dossier/fichier en octets')
    #document_ids = fields.One2many('document.fichier', 'fichier_id' , string='doc')
    #fichiers = fields.Many2many("ir.attachment")




