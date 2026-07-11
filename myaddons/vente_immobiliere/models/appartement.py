# -*- coding: utf-8 -*-
from odoo import models, fields, api


class VenteAppartement(models.Model):
    _name = 'vente.appartement'
    _description = 'Appartement'
    _inherit = ['mail.thread']
    _order = 'projet_id, bloc_id, etage_id, name'

    name = fields.Char(string='Numéro / Code', required=True, tracking=True)
    etage_id = fields.Many2one('vente.etage', string='Étage', required=True, ondelete='cascade')
    bloc_id = fields.Many2one(related='etage_id.bloc_id', string='Bloc', store=True, readonly=True)
    projet_id = fields.Many2one(related='etage_id.projet_id', string='Projet', store=True, readonly=True)

    type = fields.Selection([
        ('f1', 'F1'),
        ('f2', 'F2'),
        ('f3', 'F3'),
        ('f4', 'F4'),
        ('f5', 'F5'),
        ('studio', 'Studio'),
        ('duplex', 'Duplex'),
    ], string='Type', tracking=True)
    surface = fields.Float(string='Surface (m²)')
    nb_pieces = fields.Integer(string='Nombre de Pièces')
    nb_salles_bain = fields.Integer(string='Nombre de Salles de Bain')
    has_balcon = fields.Boolean(string='Balcon')
    orientation = fields.Selection([
        ('nord', 'Nord'),
        ('sud', 'Sud'),
        ('est', 'Est'),
        ('ouest', 'Ouest'),
    ], string='Orientation')
    has_parking = fields.Boolean(string='Parking')
    parking_number = fields.Char(string='Numéro de Parking')
    price = fields.Monetary(string='Prix', currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Devise',
                                  related='projet_id.currency_id', store=True)
    description = fields.Text(string='Description')
    plan_image = fields.Binary(string='Plan')
    niveau_finition = fields.Selection([
        ('gros_oeuvre', 'Gros Oeuvre'),
        ('semi_fini', 'Semi Fini'),
        ('fini', 'Fini'),
        ('haut_standing', 'Haut Standing'),
    ], string='Niveau de Finition')
    date_livraison = fields.Date(string='Date de Livraison')
    state = fields.Selection([
        ('disponible', 'Disponible'),
        ('reserve', 'Réservé'),
        ('vendu', 'Vendu'),
    ], string='État', default='disponible', tracking=True)
    reservation_ids = fields.One2many('vente.reservation', 'appartement_id', string='Réservations')
    active = fields.Boolean(string='Actif', default=True)
