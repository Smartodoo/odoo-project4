# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from datetime import datetime


class Documentfichier(models.Model):
    _name = 'document.fichier'
    _description = 'document(dossier_fichier)'
    _order = 'name'

    name = fields.Char(string='Nom de dossier', required=True)
    files_id = fields.Many2one('document.page', string='Dossier parent', ondelete='cascade')#RECUPERER LE NOM PARENT
    nom_dossier = fields.Char(string="dossier parent", compute='_compute_nom_dossier', store=True)
    detenteur_id = fields.Many2one('res.users', string="Détenteur", default=lambda self: self.env.uid, readonly=True)
    mise_a_jour = fields.Datetime(string='Mise à jour le', default=fields.Datetime.now,
                                  help='Date et heure de la dernière modification', readonly=True)
    taille_de_fichier = fields.Integer(string='Taille (octets)', help='Taille du dossier/fichier en octets')
    fichier = fields.Binary(string="Fichier")
    attachment_ids = fields.Many2many('ir.attachment', string='télécharger')
    partner_id = fields.Many2one(
        'res.partner',
        string="Sous-traitants",
    )
    fournisseurs_ids = fields.Many2one(
        'res.partner',
        string="Fournisseurs"

    )
    project_id = fields.Many2one ( 'custom.project',string = "Projets")

    @api.model
    def create(self, vals):
        ctx = dict(self._context or {})

        if not vals.get('partner_id'):
            partner_id = ctx.get('partner_id') or ctx.get('default_partner_id')

            if partner_id:
                vals['partners_ids'] = partner_id

        return super(Documentfichier, self).create(vals)

    @api.model
    def _search(self, args, offset=0, limit=None, order=None):

        ctx = self.env.context

        # Filtrage par Partner (logique existante)
        if ctx.get('filter_from_partner'):
            partner_id = ctx.get('default_partner_id')
            if partner_id:
                args = [('partner_id', '=', partner_id)] + args

        #   Filtrage par Project (nouvelle logique)
        if ctx.get('filter_from_project'):
            project_id = ctx.get('default_project_id')
            if project_id:
                args = [('project_id', '=', project_id)] + args

        return super()._search(args, offset=offset, limit=limit, order=order)

    @api.depends('files_id')
    def _compute_nom_dossier(self):
        for record in self:
            record.nom_dossier = record.files_id.name if record.files_id else False

    def action_open_fichier_form(self):
        self.ensure_one()  # pour être sûr qu'il n'y a qu'un record
        return {
            'type': 'ir.actions.act_window',
            'name': 'Fichier',
            'res_model': 'document.fichier',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }
