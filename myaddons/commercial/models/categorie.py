from odoo import models, fields, api


class CommercialCategorie(models.Model):
    _name = 'commercial.categorie'
    _description = 'Catégorie'
    _rec_name = 'categorie'

    type_lot_id = fields.Many2one(
        'commercial.type.lot', string="Type de lot", required=True, ondelete='cascade')
    nature_id = fields.Many2one(
        'commercial.nature.categorie', string="Nature", required=True, ondelete='cascade')
    categorie = fields.Char(
        string="Catégorie", compute='_compute_categorie', store=True)
    surface_01 = fields.Float(string="Surface 01 (m²)")
    prix_surface_01 = fields.Float(string="Prix Surface 01")
    surface_02 = fields.Float(string="Surface 02 (m²)")
    prix_surface_02 = fields.Float(string="Prix Surface 02")
    etage_id = fields.Many2one(
        'commercial.etage', string="Étage", ondelete='cascade')
    lot_ids = fields.One2many(
        'commercial.lot', 'categorie_id', string="Lots")

    @api.depends('type_lot_id', 'nature_id')
    def _compute_categorie(self):
        for rec in self:
            type_name = rec.type_lot_id.name or ''
            nature_name = rec.nature_id.name or ''
            if type_name and nature_name:
                rec.categorie = "%s.%s" % (type_name, nature_name)
            else:
                rec.categorie = type_name or nature_name or ''
