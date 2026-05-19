from odoo import models, fields, api


class CommercialListeAttenteLocation(models.Model):
    _name = 'commercial.liste.attente.location'
    _description = "Liste d'attente Location"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # --- Fiche client ---
    image_1920 = fields.Image(string="Photo", max_width=1920, max_height=1920)
    name = fields.Char(string="Nom et Prénom", required=True, tracking=True)
    genre = fields.Selection([
        ('homme', 'Homme'),
        ('femme', 'Femme'),
    ], string="Genre")
    telephone = fields.Char(string="Téléphone")
    email = fields.Char(string="Email")
    date_naissance = fields.Date(string="Date de naissance")
    lieu_naissance = fields.Char(string="Lieu de naissance")
    pays_naissance = fields.Many2one('res.country', string="Pays de naissance")
    numero_acte_naissance = fields.Char(string="N° acte de naissance")
    adresse = fields.Text(string="Adresse")

    # --- Lots intéressés ---
    lot_ids = fields.Many2many(
        'commercial.lot', 'liste_attente_location_lot_rel',
        'liste_attente_id', 'lot_id',
        string="Lots intéressés")

    lot_display = fields.Char(
        string="Lots", compute='_compute_lot_projet_display', store=True)
    projet_display = fields.Char(
        string="Projets", compute='_compute_lot_projet_display', store=True)

    @api.depends('lot_ids', 'lot_ids.numero_lot', 'lot_ids.projet_id')
    def _compute_lot_projet_display(self):
        for rec in self:
            if rec.lot_ids:
                rec.lot_display = ', '.join(
                    rec.lot_ids.mapped(lambda l: l.numero_lot or ''))
                projets = list(dict.fromkeys(
                    rec.lot_ids.mapped(lambda l: l.projet_id.name or '')))
                rec.projet_display = ', '.join(projets)
            else:
                rec.lot_display = False
                rec.projet_display = False

    # Champs de filtre pour la barre de recherche (non stockés)
    commercial_projet_id = fields.Many2one(
        'commercial.projet', string='Projet', store=False)
    commercial_bloc_id = fields.Many2one(
        'commercial.bloc', string='Bloc', store=False)
    commercial_etage_id = fields.Many2one(
        'commercial.etage', string='Étage', store=False)

    remarque = fields.Text(string="Remarque")
    commercial_id = fields.Many2one('res.users', string="Commercial",
                                    default=lambda self: self.env.user)
