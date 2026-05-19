from odoo import models, fields, api


class CommercialLot(models.Model):
    _name = 'commercial.lot'
    _description = 'Lot'

    # --- En-tête ---
    numero_lot = fields.Char(string="N° lot", required=True)
    code_perso = fields.Char(string="Code perso")
    numero_porte = fields.Char(string="N° de porte")

    # --- Emplacement ---
    projet_id = fields.Many2one(
        'commercial.projet', string="Projet", required=True, ondelete='cascade')
    bloc_id = fields.Many2one(
        'commercial.bloc', string="Bloc",
        domain="[('projet_id', '=', projet_id)]")
    etage_id = fields.Many2one(
        'commercial.etage', string="Étage",
        domain="[('bloc_id', '=', bloc_id)]")
    categorie_id = fields.Many2one(
        'commercial.categorie', string="Catégorie",
        domain="[('etage_id', '=', etage_id)]")


    @api.onchange('etage_id')
    def _onchange_etage_id(self):
        self.categorie_id = False

    @api.onchange('categorie_id')
    def _onchange_categorie_id(self):
        if self.categorie_id:
            self.surface_01 = self.categorie_id.surface_01
            self.prix_m2_surface_01 = self.categorie_id.prix_surface_01
            self.surface_02 = self.categorie_id.surface_02
            self.prix_m2_surface_02 = self.categorie_id.prix_surface_02

    # --- Superficies ---
    surface_01 = fields.Float(string="Surface 01 (m²)")
    prix_m2_surface_01 = fields.Float(string="Prix Surface 01/m²")
    surface_02 = fields.Float(string="Surface 02 (m²)")
    prix_m2_surface_02 = fields.Float(string="Prix Surface 02/m²")
    surface_globale = fields.Float(
        string="Surface globale (m²)", compute='_compute_surface_globale', store=True)
    prix_m2_global = fields.Float(
        string="Prix global/m²", compute='_compute_prix_m2_global', store=True)
    montant_surface_01 = fields.Float(
        string="Montant Surface 01", compute='_compute_montants', store=True)
    montant_surface_02 = fields.Float(
        string="Montant Surface 02", compute='_compute_montants', store=True)
    montant_global = fields.Float(
        string="Montant global", compute='_compute_montants', store=True)
    consistance = fields.Text(string="Consistance")
    quot_part_1 = fields.Float(string="Quot-part 1")
    quot_part_2 = fields.Float(string="Quot-part 2")
    quot_part_3 = fields.Float(string="Quot-part 3")

    # --- Déclaration fiscale ---
    prix_m2_fiscal_1 = fields.Float(string="Prix surface 1/m²")
    prix_m2_ht_fiscal_1 = fields.Float(string="Prix HT surface 1/m²")
    prix_m2_fiscal_2 = fields.Float(string="Prix surface 2/m²")
    prix_m2_ht_fiscal_2 = fields.Float(string="Prix HT surface 2/m²")
    montant_declare = fields.Float(string="Montant déclaré")
    tva = fields.Float(string="T.V.A")
    montant_ht = fields.Float(string="Montant HT")

    @api.depends('surface_01', 'surface_02')
    def _compute_surface_globale(self):
        for rec in self:
            rec.surface_globale = rec.surface_01 + rec.surface_02

    @api.depends('prix_m2_surface_01', 'prix_m2_surface_02')
    def _compute_prix_m2_global(self):
        for rec in self:
            rec.prix_m2_global = rec.prix_m2_surface_01 + rec.prix_m2_surface_02

    @api.depends('surface_01', 'prix_m2_surface_01', 'surface_02', 'prix_m2_surface_02')
    def _compute_montants(self):
        for rec in self:
            rec.montant_surface_01 = rec.surface_01 * rec.prix_m2_surface_01
            rec.montant_surface_02 = rec.surface_02 * rec.prix_m2_surface_02
            rec.montant_global = rec.montant_surface_01 + rec.montant_surface_02
