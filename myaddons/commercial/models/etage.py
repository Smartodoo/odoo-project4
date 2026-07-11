from odoo import models, fields, api


class CommercialEtage(models.Model):
    _name = 'commercial.etage'
    _description = 'Étage'
    _rec_name = 'etiquette'
    _order = 'sequence, id'

    sequence = fields.Integer(string="Séquence", default=10)
    name = fields.Char(string="Nom")
    niveau = fields.Char(string="Niveau")
    etiquette = fields.Char(string="Étiquette")
    numero = fields.Integer(string="Numéro")
    bloc_id = fields.Many2one(
        'commercial.bloc', string="Bloc", ondelete='cascade')
    projet_id = fields.Many2one(
        related='bloc_id.projet_id', string="Projet", store=True)
    type_etage = fields.Selection([
        ('rdc', 'RDC'),
        ('etage', 'Étage'),
        ('sous_sol', 'Sous-sol'),
        ('mezzanine', 'Mezzanine'),
        ('entresol', 'Entresol'),
        ('terrasse', 'Terrasse'),
    ], string="Type d'étage")
    nombre_logements = fields.Integer(
        string="Nombre de logements", compute='_compute_nombre_logements', store=True)
    categorie_ids = fields.One2many(
        'commercial.categorie', 'etage_id', string="Catégories")
    categorie_count = fields.Integer(
        string="Nombre de catégories", compute='_compute_categorie_count')

    @api.depends('categorie_ids')
    def _compute_nombre_logements(self):
        for rec in self:
            rec.nombre_logements = len(rec.categorie_ids)

    @api.depends('categorie_ids')
    def _compute_categorie_count(self):
        for rec in self:
            rec.categorie_count = len(rec.categorie_ids)

    def action_open_form(self):
        self.ensure_one()
        return self.action_view_categories()

    def action_view_categories(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Catégories',
            'res_model': 'commercial.categorie',
            'view_mode': 'tree,form',
            'domain': [('etage_id', '=', self.id)],
            'context': {'default_etage_id': self.id},
        }
