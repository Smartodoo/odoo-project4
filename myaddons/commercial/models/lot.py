from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class CommercialLot(models.Model):
    _name = 'commercial.lot'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Lot'
    _rec_name = 'numero_lot'
    _sql_constraints = [
        ('unique_numero_lot_bloc', 'UNIQUE(numero_lot, bloc_id)',
         'Un lot avec ce numéro existe déjà dans ce bloc.'),

    ]

    # --- Statut ---
    state = fields.Selection([
        ('disponible', 'Disponible'),
        ('en_option', 'Pré-réservé'),
        ('reserve', 'Réservé'),
        ('loue', 'Loué'),
        ('vendu', 'Vendu'),
    ], string="Statut", default='disponible', tracking=True)

    # --- Source ---
    source = fields.Selection([
        ('aucun', 'Aucun'),
        ('messenger', 'Messenger'),
        ('marketplace', 'Marketplace'),
        ('facebook', 'Page Facebook'),
        ('site_web', 'Site web'),
        ('ouedkniss', 'Ouedkniss'),
        ('instagram', 'Instagram'),
        ('twitter', 'Twitter'),
        ('recommandation', 'Recommandation (bouche à oreilles)'),
        ('foires_salons', 'Foires/Salons'),
        ('publicite', 'Publicité'),
        ('apporteur', "Apporteur d'affaires"),
        ('seminaire', 'Séminaire'),
        ('bureau_vente', 'Via le bureau de vente'),
        ('ne_sais_pas', 'Ne sais pas'),
        ('autre', 'Autre'),
    ], string="Source")

    # --- En-tête ---
    numero_lot = fields.Char(string="N° lot", required=True)
    code_perso = fields.Char(string="Code perso")
    numero_porte = fields.Char(string="N° de porte")
    montant_mensuel = fields.Float(string="Montant mensuel")
    is_location = fields.Boolean(
        string="Projet Location", compute='_compute_is_location', store=True)

    # --- Emplacement ---
    projet_id = fields.Many2one(
        'commercial.projet', string="Projet", required=True, ondelete='cascade')
    bloc_id = fields.Many2one(
        'commercial.bloc', string="Bloc",
        domain="[('projet_id', '=', projet_id)]")
    etage_id = fields.Many2one(
        'commercial.etage', string="Étage",
        domain="[('bloc_id', '=', bloc_id), '|', ('id', 'not in', full_etage_ids), ('id', '=', etage_id)]")
    categorie_id = fields.Many2one(
        'commercial.categorie', string="Catégorie",
        domain="[('etage_id', '=', etage_id), '|', ('lot_ids', '=', False), ('id', '=', categorie_id)]")
    full_etage_ids = fields.Many2many(
        'commercial.etage', compute='_compute_full_etage_ids')

    @api.depends('projet_id', 'bloc_id')
    def _compute_full_etage_ids(self):
        for rec in self:
            if rec.projet_id and rec.bloc_id:
                origin_id = rec._origin.id if isinstance(rec._origin.id, int) else False
                domain = [('projet_id', '=', rec.projet_id.id), ('categorie_id', '!=', False)]
                if origin_id:
                    domain.append(('id', '!=', origin_id))
                used_cat_ids = set(
                    self.env['commercial.lot'].search(domain).mapped('categorie_id').ids)
                full = self.env['commercial.etage']
                for etage in rec.bloc_id.etage_ids:
                    if etage.categorie_ids and set(etage.categorie_ids.ids) <= used_cat_ids:
                        full |= etage
                rec.full_etage_ids = full
            else:
                rec.full_etage_ids = self.env['commercial.etage']

    @api.onchange('bloc_id')
    def _onchange_bloc_id(self):
        self.etage_id = False
        self.categorie_id = False

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

    @api.depends('projet_id.type_projet_ids')
    def _compute_is_location(self):
        location_type = self.env.ref('commercial.commercial_type_projet_location', raise_if_not_found=False)
        for rec in self:
            if location_type and rec.projet_id:
                rec.is_location = location_type in rec.projet_id.type_projet_ids
            else:
                rec.is_location = False

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
        string="Montant global", compute='_compute_montants', store=True, readonly=False)

    consistance = fields.Text(string="Consistance")
    quot_part_1 = fields.Float(string="Quot-part 1")
    quot_part_2 = fields.Float(string="Quot-part 2")
    quot_part_3 = fields.Float(string="Quot-part 3")

    # --- Déclaration fiscale ---
    prix_m2_fiscal_1 = fields.Float(string="Prix surface 1/m²")
    prix_m2_ht_fiscal_1 = fields.Float(
        string="Prix HT surface 1/m²",
        compute='_compute_prix_ht_fiscal', store=True)
    prix_m2_fiscal_2 = fields.Float(string="Prix surface 2/m²")
    prix_m2_ht_fiscal_2 = fields.Float(
        string="Prix HT surface 2/m²",
        compute='_compute_prix_ht_fiscal', store=True)
    montant_declare = fields.Float(
        string="Montant déclaré",
        compute='_compute_declaration_fiscale', store=True)
    tva = fields.Selection([
        ('9', '9 %'),
        ('19', '19 %'),
    ], string="T.V.A",
        compute='_compute_declaration_fiscale', store=True)
    montant_ht = fields.Float(
        string="Montant HT",
        compute='_compute_declaration_fiscale', store=True)

    @api.depends('prix_m2_fiscal_1', 'surface_01', 'prix_m2_fiscal_2', 'surface_02')
    def _compute_prix_ht_fiscal(self):
        for rec in self:
            rec.prix_m2_ht_fiscal_1 = rec.prix_m2_fiscal_1 * rec.surface_01
            rec.prix_m2_ht_fiscal_2 = rec.prix_m2_fiscal_2 * rec.surface_02

    @api.depends('prix_m2_ht_fiscal_1', 'prix_m2_ht_fiscal_2', 'categorie_id.type_lot_id')
    def _compute_declaration_fiscale(self):
        for rec in self:
            rec.montant_declare = rec.prix_m2_ht_fiscal_1 + rec.prix_m2_ht_fiscal_2
            type_name = (rec.categorie_id.type_lot_id.name or '').strip().lower()
            if type_name in ('service', 'local'):
                rec.tva = '19'
                taux = 0.19
            else:
                rec.tva = '9'
                taux = 0.09
            rec.montant_ht = rec.montant_declare - (rec.montant_declare * taux)

    # --- Remise ---
    remise = fields.Float(string="Remise", default=0.0, tracking=True)

    # --- Locations ---
    location_ids = fields.One2many('commercial.location', 'lot_id', string="Contrats location")

    # --- Paiements ---
    paiement_ids = fields.One2many('commercial.paiement', 'lot_id', string="Paiements")
    paiement_count = fields.Integer(string="Nombre de paiements", compute='_compute_paiement_count')

    # --- Versements ---
    versement_ids = fields.One2many('commercial.versement', 'lot_id', string="Versements")

    # --- Champs calculés pour les cartes ---
    total_versements_confirmes = fields.Float(
        string="Total versements confirmés",
        compute='_compute_total_versements_confirmes', store=True)
    montant_net_client = fields.Float(
        string="Montant net client",
        compute='_compute_montant_net_client', store=True)

    # --- Client associé ---
    client_id = fields.Many2one(
        'res.partner', string="Client associé",
        compute='_compute_client_id')

    # --- Contacts intéressés ---
    current_partner_ids = fields.Many2many(
        'res.partner', string="Contacts actuels",
        compute='_compute_interested_partners')
    history_partner_ids = fields.Many2many(
        'res.partner', string="Anciens intéressés",
        compute='_compute_interested_partners')
    interested_partner_count = fields.Integer(
        string="Nb intéressés", compute='_compute_interested_partners')

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

    @api.depends('versement_ids.state', 'versement_ids.montant')
    def _compute_total_versements_confirmes(self):
        for rec in self:
            rec.total_versements_confirmes = sum(
                v.montant for v in rec.versement_ids if v.state == 'confirme')

    @api.depends('montant_global', 'remise')
    def _compute_montant_net_client(self):
        for rec in self:
            rec.montant_net_client = rec.montant_global - rec.remise

    def write(self, vals):
        res = super().write(vals)
        if 'montant_global' in vals or 'remise' in vals:
            for rec in self:
                rec.montant_net_client = rec.montant_global - rec.remise
            self.env.flush_all()
            paiements = self.env['commercial.paiement'].search([('lot_id', 'in', self.ids)])
            for p in paiements:
                p.montant_lot = p.lot_id.montant_net_client
        return res

    @api.depends('paiement_ids')
    def _compute_paiement_count(self):
        for rec in self:
            rec.paiement_count = len(rec.paiement_ids)

    def _compute_client_id(self):
        for rec in self:
            partner = self.env['res.partner'].search(
                [('commercial_lot_ids', 'in', rec.id)], limit=1)
            rec.client_id = partner

    def _compute_interested_partners(self):
        Partner = self.env['res.partner']
        for rec in self:
            current = Partner.search([('commercial_lot_ids', 'in', rec.id)])
            history = Partner.search([('commercial_lot_history_ids', 'in', rec.id)])
            rec.current_partner_ids = current
            rec.history_partner_ids = history - current
            rec.interested_partner_count = len(current | history)

    def unlink(self):
        for rec in self:
            partner = self.env['res.partner'].search(
                [('commercial_lot_ids', 'in', rec.id)], limit=1)
            if partner:
                raise UserError(
                    "Impossible de supprimer le lot '%s' car il est associé au contact '%s'."
                    % (rec.numero_lot, partner.name))
        return super().unlink()

    def action_view_versements(self):
        self.ensure_one()
        if self.montant_net_client <= 0:
            raise UserError("Impossible d'ouvrir les versements : le montant du lot doit être supérieur à 0.")
        # Use the partner from the active context (contact form) if available
        partner_id = self.env.context.get('active_partner_id')
        if not partner_id:
            partner = self.env['res.partner'].search(
                [('commercial_lot_ids', 'in', self.id)], limit=1)
            partner_id = partner.id if partner else False
        return {
            'type': 'ir.actions.act_window',
            'name': 'Versements',
            'res_model': 'commercial.versement',
            'view_mode': 'tree,form',
            'domain': [('lot_id', '=', self.id), ('client_id', '=', partner_id)],
            'context': {
                'default_lot_id': self.id,
                'default_projet_id': self.projet_id.id,
                'default_bloc_id': self.bloc_id.id if self.bloc_id else False,
                'default_client_id': partner_id,
            },
        }

    def action_view_paiements(self):
        self.ensure_one()
        if self.montant_net_client <= 0:
            raise UserError("Impossible d'ouvrir les paiements : le montant du lot doit être supérieur à 0.")
        # Use the partner from the active context (contact form) if available
        partner_id = self.env.context.get('active_partner_id')
        if not partner_id:
            partner = self.env['res.partner'].search(
                [('commercial_lot_ids', 'in', self.id)], limit=1)
            partner_id = partner.id if partner else False
        paiement = self.env['commercial.paiement'].search(
            [('lot_id', '=', self.id), ('client_id', '=', partner_id)], limit=1)
        if not paiement:
            paiement = self.env['commercial.paiement'].create({
                'lot_id': self.id,
                'client_id': partner_id,
            })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Fiche Paiement',
            'res_model': 'commercial.paiement',
            'view_mode': 'form',
            'res_id': paiement.id,
        }

    def action_view_location(self):
        self.ensure_one()
        client_location_id = self.env.context.get('client_location_id', False)
        client_name = self.env.context.get('client_location_name', '')
        domain = [('lot_id', '=', self.id)]
        ctx = {
            'default_lot_id': self.id,
            'default_montant_mensuel': self.montant_mensuel,
        }
        if client_location_id:
            domain.append(('client_location_id', '=', client_location_id))
            ctx['default_client_location_id'] = client_location_id
        tree_view = self.env.ref('commercial.commercial_location_view_tree')
        form_view = self.env.ref('commercial.commercial_location_view_form')
        search_view = self.env.ref('commercial.commercial_location_view_search')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Contrats de Location',
            'res_model': 'commercial.location',
            'view_mode': 'tree,form',
            'views': [(tree_view.id, 'tree'), (form_view.id, 'form')],
            'search_view_id': [search_view.id, 'search'],
            'domain': domain,
            'context': ctx,
        }
