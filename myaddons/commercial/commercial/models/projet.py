from odoo import models, fields, api


WILAYAS = [
    ('01', 'Adrar'), ('02', 'Chlef'), ('03', 'Laghouat'), ('04', 'Oum El Bouaghi'),
    ('05', 'Batna'), ('06', 'Béjaïa'), ('07', 'Biskra'), ('08', 'Béchar'),
    ('09', 'Blida'), ('10', 'Bouira'), ('11', 'Tamanrasset'), ('12', 'Tébessa'),
    ('13', 'Tlemcen'), ('14', 'Tiaret'), ('15', 'Tizi Ouzou'), ('16', 'Alger'),
    ('17', 'Djelfa'), ('18', 'Jijel'), ('19', 'Sétif'), ('20', 'Saïda'),
    ('21', 'Skikda'), ('22', 'Sidi Bel Abbès'), ('23', 'Annaba'), ('24', 'Guelma'),
    ('25', 'Constantine'), ('26', 'Médéa'), ('27', 'Mostaganem'), ('28', "M'Sila"),
    ('29', 'Mascara'), ('30', 'Ouargla'), ('31', 'Oran'), ('32', 'El Bayadh'),
    ('33', 'Illizi'), ('34', 'Bordj Bou Arréridj'), ('35', 'Boumerdès'),
    ('36', 'El Tarf'), ('37', 'Tindouf'), ('38', 'Tissemsilt'), ('39', 'El Oued'),
    ('40', 'Khenchela'), ('41', 'Souk Ahras'), ('42', 'Tipaza'), ('43', 'Mila'),
    ('44', 'Aïn Defla'), ('45', 'Naâma'), ('46', 'Aïn Témouchent'), ('47', 'Ghardaïa'),
    ('48', 'Relizane'), ('49', 'El M\'Ghair'), ('50', 'El Meniaa'),
    ('51', 'Ouled Djellal'), ('52', 'Bordj Badji Mokhtar'), ('53', 'Béni Abbès'),
    ('54', 'Timimoun'), ('55', 'Touggourt'), ('56', 'Djanet'),
    ('57', 'In Salah'), ('58', 'In Guezzam'),
]


class CommercialProjet(models.Model):
    _name = 'commercial.projet'
    _description = 'Projet Immobilier'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Nom du projet", required=True, tracking=True)

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
    description = fields.Text(string="Description")

    # --- Section 2: Localisation ---
    pays_id = fields.Many2one('res.country', string="Pays")
    wilaya = fields.Selection(WILAYAS, string="Wilaya")
    lieu_dit = fields.Char(string="Lieu-dit / Quartier / Cité")
    repere = fields.Char(string="Repère")
    adresse = fields.Char(string="Adresse")
    superficie_terrain = fields.Float(string="Superficie du terrain (m²)")

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

    # --- Relations ---
    bloc_ids = fields.One2many('commercial.bloc', 'projet_id', string="Blocs")
    lot_ids = fields.One2many('commercial.lot', 'projet_id', string="Lots")
    bloc_count = fields.Integer(string="Nombre de blocs", compute='_compute_bloc_count')
    lot_count = fields.Integer(string="Nombre de lots", compute='_compute_lot_count')

    # --- Champs standards ---
    company_id = fields.Many2one(
        'res.company', string="Société", default=lambda self: self.env.company)
    user_id = fields.Many2one(
        'res.users', string="Responsable", default=lambda self: self.env.user)

    @api.depends('bloc_ids')
    def _compute_bloc_count(self):
        for rec in self:
            rec.bloc_count = len(rec.bloc_ids)

    @api.depends('lot_ids')
    def _compute_lot_count(self):
        for rec in self:
            rec.lot_count = len(rec.lot_ids)

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
