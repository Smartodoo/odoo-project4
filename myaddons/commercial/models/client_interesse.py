import logging

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CommercialClientInteresse(models.Model):
    _name = 'commercial.client.interesse'
    _description = 'Client intéressé par projet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'numero asc'

    numero = fields.Integer(string="N°", tracking=True)
    date = fields.Date(string="Date", tracking=True)
    nom_prenom = fields.Char(string="Nom et Prénom", tracking=True)
    telephone = fields.Char(string="Téléphone")
    email = fields.Char(string="Email")
    fonction = fields.Char(string="Fonction")
    interesse_projet = fields.Char(string="Projet")
    interesse_bloc = fields.Char(string="Bloc")
    interesse_etage = fields.Char(string="Étage")
    interesse_type = fields.Char(string="Type")
    commercial_id = fields.Many2one('res.users', string="Nom du commercial",
                                     default=lambda self: self.env.user)
    remarque = fields.Text(string="Remarque")
    observation = fields.Text(string="Observation")
    communication_ids = fields.One2many(
        'commercial.communication', 'client_interesse_id',
        string="Communications")
    communication_count = fields.Integer(
        string="Nb communications", compute='_compute_communication_count')
    state = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('valide', 'Validé'),
    ], string="État", default='brouillon', tracking=True)
    partner_id = fields.Many2one('res.partner', string="Contact créé", readonly=True)

    @api.depends('communication_ids')
    def _compute_communication_count(self):
        for rec in self:
            rec.communication_count = len(rec.communication_ids)

    def action_valider(self):
        self.ensure_one()
        if self.state == 'valide':
            raise UserError("Ce client intéressé a déjà été validé.")
        if not self.nom_prenom:
            raise UserError("Le champ 'Nom et Prénom' est obligatoire pour valider.")
        # Vérifier que le projet saisi existe dans commercial.projet
        if not self.interesse_projet:
            raise UserError("Le champ 'Projet' (Intéressé par) est obligatoire pour valider.")
        projet = self.env['commercial.projet'].search(
            [('name', '=ilike', self.interesse_projet.strip())], limit=1)
        if not projet:
            raise UserError(
                "Le projet '%s' n'existe pas dans la liste des projets commerciaux."
                % self.interesse_projet)
        # Créer le contact externe (pré-réservation)
        partner = self.env['res.partner'].create({
            'name': self.nom_prenom,
            'phone': self.telephone or False,
            'email': self.email or False,
            'function': self.fonction or False,
            'contact_category': 'interne',
            'type_client_commercial': 'Visiteur',
            'commercial_user_id': self.commercial_id.id if self.commercial_id else False,
        })
        # Chercher et associer le lot si les champs intéressé par sont remplis
        _logger.info("=== VALIDATION LOT === projet=%s, bloc=%s, etage=%s, type=%s",
                      self.interesse_projet, self.interesse_bloc, self.interesse_etage, self.interesse_type)
        if self.interesse_projet and self.interesse_bloc and self.interesse_etage and self.interesse_type:
            int_projet = self.env['commercial.projet'].search(
                [('name', '=ilike', self.interesse_projet.strip())], limit=1)
            _logger.info("Projet trouvé: %s (id=%s)", int_projet.name if int_projet else 'NON', int_projet.id if int_projet else 0)
            if int_projet:
                int_bloc = self.env['commercial.bloc'].search([
                    ('projet_id', '=', int_projet.id),
                    '|',
                    ('name', '=ilike', self.interesse_bloc.strip()),
                    ('code', '=ilike', self.interesse_bloc.strip()),
                ], limit=1)
                _logger.info("Bloc trouvé: %s (id=%s)", int_bloc.name if int_bloc else 'NON', int_bloc.id if int_bloc else 0)
                if int_bloc:
                    int_etage = self.env['commercial.etage'].search([
                        ('bloc_id', '=', int_bloc.id),
                        '|', '|',
                        ('name', '=ilike', self.interesse_etage.strip()),
                        ('etiquette', '=ilike', self.interesse_etage.strip()),
                        ('niveau', '=ilike', self.interesse_etage.strip()),
                    ], limit=1)
                    _logger.info("Étage trouvé: %s (id=%s)", int_etage.name if int_etage else 'NON', int_etage.id if int_etage else 0)
                    if int_etage:
                        # Chercher la catégorie par son nom (ex: APPARTEMENT.F4.P)
                        int_categorie = self.env['commercial.categorie'].search([
                            ('etage_id', '=', int_etage.id),
                            ('categorie', '=ilike', self.interesse_type.strip()),
                        ], limit=1)
                        _logger.info("Catégorie trouvée: %s (id=%s)", int_categorie.categorie if int_categorie else 'NON', int_categorie.id if int_categorie else 0)
                        if int_categorie:
                            lot = self.env['commercial.lot'].search([
                                ('projet_id', '=', int_projet.id),
                                ('bloc_id', '=', int_bloc.id),
                                ('etage_id', '=', int_etage.id),
                                ('categorie_id', '=', int_categorie.id),
                                ('state', '=', 'disponible'),
                            ], limit=1)
                            _logger.info("Lot trouvé: %s (id=%s, state=%s)", lot.numero_lot if lot else 'NON', lot.id if lot else 0, lot.state if lot else '')
                            if lot:
                                partner.write({
                                    'commercial_lot_ids': [(4, lot.id)],
                                })
                                _logger.info("Lot %s associé au contact %s", lot.numero_lot, partner.name)
        self.write({
            'state': 'valide',
            'partner_id': partner.id,
        })
        # Ouvrir la fiche contact créée
        return {
            'type': 'ir.actions.act_window',
            'name': partner.name,
            'res_model': 'res.partner',
            'view_mode': 'form',
            'res_id': partner.id,
            'target': 'current',
            'context': {
                'default_contact_category': 'interne',
                'is_contact_externe': True,
            },
        }

    def action_open_partner(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.partner_id.name,
            'res_model': 'res.partner',
            'view_mode': 'form',
            'res_id': self.partner_id.id,
            'target': 'current',
            'context': {
                'default_contact_category': 'interne',
                'is_contact_externe': True,
            },
        }

    def action_view_communications(self):
        self.ensure_one()
        wizard = self.env['commercial.communication.interesse.wizard'].create({
            'client_interesse_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Communications',
            'res_model': 'commercial.communication.interesse.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }


class CommercialCommunicationInherit(models.Model):
    _inherit = 'commercial.communication'

    client_interesse_id = fields.Many2one(
        'commercial.client.interesse', string="Client intéressé",
        ondelete='cascade')
