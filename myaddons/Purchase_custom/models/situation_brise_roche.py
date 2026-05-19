from odoo import fields, models, api


class SituationBriseRoche(models.Model):
    _name = 'situation.brise.roche'
    _description = 'Situation Brise Roche'
    _order = 'date desc'

    name = fields.Char(string="Référence", readonly=True, default='Nouveau', copy=False)
    date = fields.Date(string="Date", required=True, default=fields.Date.context_today)
    type_engin = fields.Char(string="Type d'engin")
    n_bon = fields.Char(string="N° Bon")
    engin = fields.Char(string="Engin")
    nombre_heures = fields.Float(string="Nombre d'heures")
    total_journalite = fields.Float(
        string="Total Journalité", compute='_compute_total_journalite', store=True,
    )
    prix_unitaire_jour = fields.Float(string="Prix unitaire de jour")
    montant = fields.Float(string="Montant", compute='_compute_montant', store=True)
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
    observation = fields.Text(string="Observation")
    designation = fields.Char(
        string="Désignation",
        help="Texte affiché dans la colonne Désignation du rapport brise roche.",
    )

    @api.depends('nombre_heures')
    def _compute_total_journalite(self):
        for record in self:
            record.total_journalite = record.nombre_heures / 8 if record.nombre_heures else 0

    @api.depends('prix_unitaire_jour', 'total_journalite')
    def _compute_montant(self):
        for record in self:
            record.montant = record.prix_unitaire_jour * record.total_journalite

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self._build_brise_reference(vals)
        return super().create(vals_list)

    def _build_brise_reference(self, vals):
        """Référence par sous-traitant : BR/<sub>/<seq>
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
        return "BR/%s/%03d" % (sub_name, seq)