from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CommercialProjet(models.Model):
    _name = 'commercial.projet'
    _description = 'Projet Immobilier'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _sql_constraints = [
        ('name_unique', 'UNIQUE(LOWER(name))', 'Un projet avec ce nom existe déjà. Veuillez choisir un nom différent.'),
    ]

    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('validated', 'Validé'),
    ], string="État", default='draft', tracking=True)

    name = fields.Char(string="Nom du projet", required=True, tracking=True)

    def action_validate(self):
        for rec in self:
            rec.state = 'validated'

    def action_set_draft(self):
        for rec in self:
            rec.state = 'draft'

    @api.constrains('name')
    def _check_name_unique_case_insensitive(self):
        for rec in self:
            if rec.name:
                duplicate = self.search([
                    ('id', '!=', rec.id),
                    ('name', '=ilike', rec.name),
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        _('Un projet avec le nom "%s" existe déjà. Veuillez choisir un nom différent.') % duplicate.name
                    )

    # --- Section 1: Informations générales ---
    intitule_administratif = fields.Char(
        string="Intitulé administratif du projet", required=True, tracking=True)
    code = fields.Char(string="Code", tracking=True)
    type_projet_ids = fields.Many2many(
        'commercial.type.projet', string="Type de projet")
    avancement = fields.Float(string="Avancement (%)")
    date_debut = fields.Date(string="Date de début")
    duree_realisation = fields.Integer(string="Durée de réalisation (mois)")
    date_achevement = fields.Date(string="Date d'achèvement")
    description = fields.Text(string="Note d'attestation provisoire")
    programme = fields.Text(string="Programme")
    emplacement_projet = fields.Text(string="Emplacement de projet")
    note_versement = fields.Text(string="Note versement")
    commodites_disponible = fields.Text(string="Commodités disponible")
    type_finition = fields.Text(string="Type de finition")

    # --- Section 2: Localisation ---
    pays_id = fields.Many2one('res.country', string="Pays")
    wilaya_id = fields.Many2one('commercial.wilaya', string="Wilaya",
                                domain="[('country_id', '=', pays_id)]")
    daira_id = fields.Many2one('commercial.daira', string="Daïra",
                               domain="[('wilaya_id', '=', wilaya_id)]")
    commune_id = fields.Many2one('commercial.commune', string="Commune",
                                 domain="[('wilaya_id', '=', wilaya_id)]")
    section = fields.Char(string="Section")
    lieu_dit = fields.Char(string="Lieu-dit / Quartier / Cité")
    repere = fields.Char(string="Repère")
    adresse = fields.Char(string="Adresse")
    superficie_terrain = fields.Float(string="Superficie du terrain (m²)")

    @api.onchange('pays_id')
    def _onchange_pays_id(self):
        if self.wilaya_id and self.wilaya_id.country_id != self.pays_id:
            self.wilaya_id = False
            self.daira_id = False
            self.commune_id = False

    @api.onchange('wilaya_id')
    def _onchange_wilaya_id(self):
        if self.daira_id and self.daira_id.wilaya_id != self.wilaya_id:
            self.daira_id = False
            self.commune_id = False

    @api.onchange('wilaya_id')
    def _onchange_wilaya_id_commune(self):
        if self.commune_id and self.commune_id.wilaya_id != self.wilaya_id:
            self.commune_id = False

    # --- Section 3-1: Identification juridique et technique ---
    conservation_fonciere = fields.Char(string="Conservation foncière")
    livret_foncier = fields.Char(string="Livret foncier")
    delivre_le = fields.Date(string="Délivré le")
    delivre_par = fields.Char(string="Délivré par")

    # --- 3-1-1: Acte notarié ---
    acte_numero_enregistrement = fields.Char(string="N° d'enregistrement")
    acte_date_publication = fields.Date(string="Date de publication")
    acte_volume = fields.Char(string="Volume")
    acte_folio = fields.Char(string="Folio")

    # --- 3-1-2: Etat descriptif de division ---
    edd_numero_enregistrement = fields.Char(string="N° d'enregistrement")
    edd_date_publication = fields.Date(string="Date de publication")
    edd_volume = fields.Char(string="Volume")
    edd_folio = fields.Char(string="Folio")
    reference_cadastrale = fields.Char(string="Référence cadastrale")

    # --- 3-2: Permis et Certificat ---
    permis_lotir_numero = fields.Char(string="N° permis de lotir")
    permis_lotir_date = fields.Date(string="Date permis de lotir")
    permis_lotir_par = fields.Char(string="Délivré par")

    certificat_amenagement_numero = fields.Char(string="N° certificat d'aménagement")
    certificat_amenagement_date = fields.Date(string="Date certificat d'aménagement")
    certificat_amenagement_par = fields.Char(string="Délivré par")

    permis_construire_numero = fields.Char(string="N° permis de construire")
    permis_construire_date = fields.Date(string="Date permis de construire")
    permis_construire_par = fields.Char(string="Délivré par")

    # --- Documents ---
    document_ids = fields.Many2many(
        'ir.attachment', string="Documents",
        help="Documents liés au projet")
    document_count = fields.Integer(
        string="Nombre de documents", compute='_compute_document_count')

    @api.depends('document_ids')
    def _compute_document_count(self):
        for rec in self:
            rec.document_count = len(rec.document_ids)

    # --- Relations ---
    bloc_ids = fields.One2many('commercial.bloc', 'projet_id', string="Blocs")
    lot_ids = fields.One2many('commercial.lot', 'projet_id', string="Lots")
    used_categorie_ids = fields.Many2many(
        'commercial.categorie', compute='_compute_used_categorie_ids')
    full_etage_ids = fields.Many2many(
        'commercial.etage', compute='_compute_full_etage_ids')
    bloc_count = fields.Integer(string="Nombre de blocs", compute='_compute_bloc_count')
    lot_count = fields.Integer(string="Nombre de lots", compute='_compute_lot_count')
    logement_count = fields.Integer(string="Nombre de logements", compute='_compute_lot_type_counts')
    parking_count = fields.Integer(string="Nombre de parkings", compute='_compute_lot_type_counts')
    client_ids = fields.One2many(
        'res.partner', 'commercial_projet_id', string="Clients",
        domain=[('type_client_commercial', '=', 'client')])

    # --- Champs standards ---
    company_id = fields.Many2one(
        'res.company', string="Société", default=lambda self: self.env.company)
    user_id = fields.Many2one(
        'res.users', string="Responsable", default=lambda self: self.env.user)

    @api.depends('lot_ids.categorie_id')
    def _compute_used_categorie_ids(self):
        for rec in self:
            rec.used_categorie_ids = rec.lot_ids.mapped('categorie_id')

    @api.depends('lot_ids.categorie_id')
    def _compute_full_etage_ids(self):
        for rec in self:
            used_cat_ids = set(rec.lot_ids.mapped('categorie_id').ids)
            full_etages = self.env['commercial.etage']
            for etage in rec.bloc_ids.mapped('etage_ids'):
                if etage.categorie_ids and set(etage.categorie_ids.ids) <= used_cat_ids:
                    full_etages |= etage
            rec.full_etage_ids = full_etages

    @api.depends('bloc_ids')
    def _compute_bloc_count(self):
        for rec in self:
            rec.bloc_count = len(rec.bloc_ids)

    @api.depends('lot_ids')
    def _compute_lot_count(self):
        for rec in self:
            rec.lot_count = len(rec.lot_ids)

    @api.depends('lot_ids.categorie_id.type_lot_id')
    def _compute_lot_type_counts(self):
        for rec in self:
            parking = 0
            logement = 0
            for lot in rec.lot_ids:
                type_name = (lot.categorie_id.type_lot_id.name or '').strip().lower()
                if type_name == 'parking':
                    parking += 1
                else:
                    logement += 1
            rec.parking_count = parking
            rec.logement_count = logement

    def action_view_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Documents',
            'res_model': 'ir.attachment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.document_ids.ids)],
        }

    def action_view_blocs(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Blocs',
            'res_model': 'commercial.bloc',
            'view_mode': 'tree,form',
            'domain': [('projet_id', '=', self.id)],
            'context': {'default_projet_id': self.id},
        }

    def action_view_lots(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lots',
            'res_model': 'commercial.lot',
            'view_mode': 'tree,form',
            'domain': [('projet_id', '=', self.id)],
            'context': {'default_projet_id': self.id},
        }

    def unlink(self):
        for projet in self:
            lots_bloques = projet.lot_ids.filtered(
                lambda l: l.state in ('en_option', 'reserve', 'vendu')
            )
            if lots_bloques:
                raise ValidationError(
                    _('Impossible de supprimer le projet "%s" car il contient des lots '
                      'pré-réservés, réservés ou vendus.') % projet.name
                )
        return super().unlink()

    def action_create_client_externe(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nouveau Client',
            'res_model': 'res.partner',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_contact_category': 'interne',
                'is_contact_externe': True,
            },
        }

    def action_print_liste_lots_filtered(self, filters=None):
        self.ensure_one()
        domain = [('projet_id', '=', self.id)]
        if filters:
            if filters.get('bloc'):
                domain.append(('bloc_id.code', 'ilike', filters['bloc']))
            if filters.get('etage'):
                domain.append(('etage_id.etiquette', 'ilike', filters['etage']))
            if filters.get('categorie'):
                domain.append(('categorie_id.categorie', 'ilike', filters['categorie']))
            if filters.get('numero_lot'):
                domain.append(('numero_lot', 'ilike', filters['numero_lot']))
            if filters.get('state'):
                domain.append(('state', '=', filters['state']))
        lots = self.env['commercial.lot'].search(domain)
        if not lots:
            return False
        return self.env.ref(
            'commercial.action_report_liste_lots'
        ).report_action(lots.ids)

