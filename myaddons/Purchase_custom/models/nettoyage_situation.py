from odoo import fields, models, api


class NettoyageSituation(models.Model):
    _name = 'nettoyage.situation'
    _description = 'Situation Nettoyage'
    _order = 'date desc'

    name = fields.Char(string="Référence", readonly=True, default='Nouveau', copy=False)
    date = fields.Date(string="Date", required=True, default=fields.Date.context_today)
    camion_id = fields.Many2one(
        'nettoyage.camion', string="Camion (Matriculation)", required=True,
    )
    chauffeur_id = fields.Many2one(
        'nettoyage.chauffeur', string="Chauffeur", required=True,
    )
    company_id = fields.Many2one(
        'res.company', string="Société",
        default=lambda self: self.env.company, index=True,
    )
    project_id = fields.Many2one('custom.project', string="Projet", required=True,
                                  domain="[('company_id', '=', allowed_company_ids[0])]")
    sous_traitant_id = fields.Many2one(
        'res.partner', string="Sous Traitant",
        domain="[('contact_type','=','SUBCONTRACTOR')]",
    )
    observation = fields.Char(
        string="Observation",
        help="Texte affiché dans la colonne Observation du rapport nettoyage.",
    )
    titre = fields.Char(
        string="Titre",
        help="Titre affiché en deuxième ligne du rapport chauffeur/camion "
             "(par défaut : EVACUATION DES TERRES VERS LA CENTRALE A BETON).",
    )

    mode_calcul = fields.Selection([
        ('heures', "Nombre d'heures"),
        ('voyages', "Nombre de voyages"),
    ], string="Mode de calcul", default='heures', required=True)

    # ===== Mode heures =====
    nombre_heures = fields.Float(string="Nombre d'heures")
    total_journalite = fields.Float(
        string="Total Journalité", compute='_compute_total_journalite', store=True,
    )
    prix_unitaire_jour = fields.Float(string="Prix unitaire de jour")

    # ===== Mode voyages =====
    nombre_voyages = fields.Float(string="Nombre de voyages")
    prix_unitaire_voyage = fields.Float(string="Prix unitaire de voyage")

    # ===== Montant calculé selon le mode =====
    montant = fields.Float(string="Montant", compute='_compute_montant', store=True)

    @api.depends('nombre_heures')
    def _compute_total_journalite(self):
        for record in self:
            record.total_journalite = record.nombre_heures / 8 if record.nombre_heures else 0

    @api.depends(
        'mode_calcul',
        'prix_unitaire_jour', 'total_journalite',
        'prix_unitaire_voyage', 'nombre_voyages',
    )
    def _compute_montant(self):
        for record in self:
            if record.mode_calcul == 'voyages':
                record.montant = (record.prix_unitaire_voyage or 0.0) * (record.nombre_voyages or 0.0)
            else:
                record.montant = (record.prix_unitaire_jour or 0.0) * (record.total_journalite or 0.0)

    @api.onchange('mode_calcul')
    def _onchange_mode_calcul(self):
        """Réinitialise les champs de l'autre mode pour éviter les valeurs résiduelles."""
        for rec in self:
            if rec.mode_calcul == 'heures':
                rec.nombre_voyages = 0.0
                rec.prix_unitaire_voyage = 0.0
            elif rec.mode_calcul == 'voyages':
                rec.nombre_heures = 0.0
                rec.prix_unitaire_jour = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self._build_nettoyage_reference(vals)
        return super().create(vals_list)

    def _build_nettoyage_reference(self, vals):
        """Référence par sous-traitant : NET/<sub>/<seq>
        Le compteur est local au sous-traitant."""
        sub_id = vals.get('sous_traitant_id')
        existing = self.sudo().search_count([
            ('sous_traitant_id', '=', sub_id),
        ])
        seq = existing + 1
        sub_name = 'NA'
        if sub_id:
            sub = self.env['res.partner'].sudo().browse(sub_id)
            if sub.exists():
                sub_name = (sub.name or 'NA').strip()[:8].upper()
        return "NET/%s/%03d" % (sub_name, seq)