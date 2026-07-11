from odoo import models, fields, api
from odoo.exceptions import UserError


class CommercialClientLocation(models.Model):
    _name = 'commercial.client.location'
    _description = 'Client Location'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'nom'

    image_1920 = fields.Image(string="Image", max_width=1920, max_height=1920)

    nom = fields.Char(string="Nom", required=True, tracking=True)
    genre = fields.Selection([
        ('homme', 'Homme'),
        ('femme', 'Femme'),
    ], string="Genre")
    date_naissance = fields.Date(string="Date de naissance")
    lieu_naissance = fields.Char(string="Lieu de naissance")
    pays_naissance = fields.Many2one('res.country', string="Pays de naissance")
    numero_acte_naissance = fields.Char(string="N° acte de naissance")
    telephone = fields.Char(string="Téléphone")
    adresse = fields.Text(string="Adresse")

    lot_ids = fields.Many2many(
        'commercial.lot', 'client_location_lot_rel', 'client_id', 'lot_id',
        string="Lots Location",
    )
    lot_autre_ids = fields.Many2many(
        'commercial.lot', 'client_location_lot_autre_rel', 'client_id', 'lot_id',
        string="Autres Lots",
    )

    # Champs de filtre pour la barre de recherche lots location
    commercial_projet_id = fields.Many2one(
        'commercial.projet', string='Projet', store=False)
    commercial_bloc_id = fields.Many2one(
        'commercial.bloc', string='Bloc', store=False)
    commercial_etage_id = fields.Many2one(
        'commercial.etage', string='Étage', store=False)
    commercial_lot_state_filter = fields.Selection([
        ('disponible', 'Disponible'),
        ('reserve', 'Réservé'),
    ], string="Filtre statut lot", store=False)

    # Champs de filtre pour la barre de recherche autres lots
    commercial_autre_projet_id = fields.Many2one(
        'commercial.projet', string='Projet', store=False)
    commercial_autre_bloc_id = fields.Many2one(
        'commercial.bloc', string='Bloc', store=False)
    commercial_autre_etage_id = fields.Many2one(
        'commercial.etage', string='Étage', store=False)

    location_ids = fields.One2many(
        'commercial.location', 'client_location_id', string="Contrats de Location")

    client_card_html = fields.Html(
        string="Carte Client", compute='_compute_client_card_html', sanitize=False)
    lot_cards_html = fields.Html(
        string="Lots en cours", compute='_compute_lot_cards_html', sanitize=False)

    company_id = fields.Many2one(
        'res.company', string="Société", default=lambda self: self.env.company)

    @api.depends('nom', 'telephone')
    def _compute_client_card_html(self):
        for rec in self:
            nom = rec.nom or ''
            tel = rec.telephone or ''
            rec.client_card_html = '''
            <div style="text-align:right;padding:4px 0;">
                <div style="font-size:18px;font-weight:700;color:#333;">%(nom)s</div>
                <div style="font-size:13px;color:#666;margin-top:2px;">%(tel)s</div>
            </div>
            ''' % {'nom': nom, 'tel': tel}

    def _compute_lot_cards_html(self):
        Location = self.env['commercial.location']
        for rec in self:
            all_lots = rec.lot_ids | rec.lot_autre_ids
            if not all_lots:
                rec.lot_cards_html = False
                continue

            contrats = Location.search([
                ('lot_id', 'in', all_lots.ids),
                ('client_location_id', '=', rec.id),
                ('state', '=', 'en_cours'),
            ])
            if not contrats:
                rec.lot_cards_html = False
                continue

            def fmt(val):
                return '{:,.2f}'.format(val).replace(',', ' ')

            cards = []
            for contrat in contrats:
                lot = contrat.lot_id
                projet_name = lot.projet_id.name or ''
                bloc_name = lot.bloc_id.code or ''
                lot_num = lot.numero_lot or ''
                type_c = dict(contrat._fields['type_contrat'].selection).get(
                    contrat.type_contrat, '')
                delais = contrat.delais or 0
                date_debut = contrat.date_debut.strftime('%d/%m/%Y') if contrat.date_debut else ''
                date_fin = contrat.date_fin.strftime('%d/%m/%Y') if contrat.date_fin else ''

                cards.append('''
                <div style="flex:1;min-width:280px;max-width:420px;
                            border:1px solid #dee2e6;border-radius:0;
                            overflow:hidden;background:#f8f9fa;">
                    <div style="padding:8px 14px;font-size:12px;font-weight:700;
                                color:#333;border-bottom:1px solid #dee2e6;">
                        %(projet)s &nbsp;|&nbsp; Bloc %(bloc)s &nbsp;|&nbsp; Lot %(lot)s
                    </div>
                    <div style="padding:10px 14px;font-size:10pt;">
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                            <span style="color:#555555;">Type de contrat</span>
                            <span style="font-weight:700;color:#4E4E4E;">%(type_contrat)s</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                            <span style="color:#555555;">Délais</span>
                            <span style="font-weight:700;color:#4E4E4E;">%(delais)s mois</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                            <span style="color:#555555;">Date début</span>
                            <span style="font-weight:700;color:#27AE60;">%(date_debut)s</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                            <span style="color:#555555;">Date fin</span>
                            <span style="font-weight:700;color:#E74C3C;">%(date_fin)s</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                            <span style="color:#555555;">Versement</span>
                            <span style="font-weight:700;color:#27AE60;">%(versement)s DA</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-top:8px;
                                    padding-top:6px;border-top:1px solid #999;">
                            <span style="font-weight:700;color:#333333;">Reste à payer</span>
                            <span style="font-weight:700;color:#F39C12;">%(reste)s DA</span>
                        </div>
                    </div>
                </div>
                ''' % {
                    'projet': projet_name,
                    'bloc': bloc_name,
                    'lot': lot_num,
                    'type_contrat': type_c,
                    'delais': delais,
                    'date_debut': date_debut,
                    'date_fin': date_fin,
                    'versement': fmt(contrat.total_versements),
                    'reste': fmt(contrat.reste_a_payer),
                })
            rec.lot_cards_html = (
                '<div style="display:flex;flex-wrap:wrap;gap:14px;'
                'margin-bottom:16px;padding:8px 0;">'
                + ''.join(cards) + '</div>'
            )

    def action_print_reglement_interieur(self):
        return self.env.ref('commercial.action_report_reglement_interieur').report_action(self)

    @api.constrains('lot_ids', 'lot_autre_ids')
    def _check_lot_loue(self):
        for rec in self:
            all_lots = rec.lot_ids | rec.lot_autre_ids
            lots_loues = all_lots.filtered(lambda l: l.state == 'loue')
            for lot in lots_loues:
                client = self.env['commercial.client.location'].search([
                    '|',
                    ('lot_ids', 'in', lot.id),
                    ('lot_autre_ids', 'in', lot.id),
                    ('id', '!=', rec.id),
                ], limit=1)
                client_name = client.nom or 'Inconnu'
                contrat = self.env['commercial.location'].search([
                    ('lot_id', '=', lot.id),
                    ('state', '=', 'en_cours'),
                ], limit=1)
                date_fin = contrat.date_fin.strftime('%d/%m/%Y') if contrat and contrat.date_fin else 'N/A'
                raise UserError(
                    "Impossible d'ajouter le lot '%s', il est déjà loué par '%s'. "
                    "Le lot sera disponible le %s."
                    % (lot.numero_lot, client_name, date_fin)
                )

