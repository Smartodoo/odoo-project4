from odoo import models, fields


class CommercialListeAttente(models.Model):
    _name = 'commercial.liste.attente'
    _description = "Liste d'attente"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # --- Fiche client ---
    name = fields.Char(string="Nom et Prénom", required=True, tracking=True)
    telephone = fields.Char(string="Téléphone")
    email = fields.Char(string="Email")

    # --- Intéressé par (champs texte libre) ---
    projet = fields.Char(string="Projet", tracking=True)
    bloc = fields.Char(string="Bloc")
    etage = fields.Char(string="Étage")
    lot = fields.Char(string="Lot")

    remarque = fields.Text(string="Remarque")
    commercial_id = fields.Many2one('res.users', string="Commercial",
                                    default=lambda self: self.env.user)
