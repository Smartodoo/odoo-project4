from odoo import models, fields, api


class CommercialPropositionTerrain(models.Model):
    _name = 'commercial.proposition.terrain'
    _description = 'Proposition terrain'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'numero asc'

    numero = fields.Integer(string="N°", tracking=True)
    date = fields.Date(string="Date", tracking=True)
    nom_prenom_proprietaire = fields.Char(
        string="Nom et Prénom du propriétaire", tracking=True)
    adresse = fields.Char(string="Adresse")
    telephone = fields.Char(string="Téléphone")
    email = fields.Char(string="Email")
    surface_utile = fields.Char(string="S.U")
    facades = fields.Char(string="Façades")
    source = fields.Char(string="Source")
    papier_notaire = fields.Char(string="Papier notaire")
    document_ids = fields.Many2many(
        'ir.attachment', 'proposition_terrain_attachment_rel',
        'proposition_id', 'attachment_id',
        string="Documents")
    prix_m2_estimation = fields.Char(string="Prix / M² Estimation")
    reunion_tenue_le = fields.Date(string="Réunion tenue le")
    compte_rendu = fields.Text(string="Compte rendu")
    observation = fields.Text(string="Observation")
    agent = fields.Char(string="Agent")
    gabarit = fields.Char(string="Gabarit")
    wilaya = fields.Char(string="Wilaya", tracking=True)
    region = fields.Char(string="Région", tracking=True)
