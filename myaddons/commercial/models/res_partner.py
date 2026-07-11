from odoo import api, fields, models
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

TYPE_CLIENT_ORDER = {
    'Visiteur': 0,
    'client': 1,
    False: 2,
}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, access_rights_uid=None):
        """Auto-exclude blocked contacts in commercial context, like active field behavior.
        Skip when active_test=False (access rule checks) to avoid access denied errors."""
        if (self.env.context.get('is_contact_externe')
                and self.env.context.get('active_test', True)):
            has_blocked = any(
                isinstance(term, (list, tuple)) and len(term) == 3 and term[0] == 'is_blocked'
                for term in domain
            )
            if not has_blocked:
                domain = [('is_blocked', '=', False)] + list(domain)
        return super()._search(domain, offset=offset, limit=limit, order=order, access_rights_uid=access_rights_uid)

    def unlink(self):
        """Bloquer la suppression si le contact a des échéances confirmées ou des versements confirmés.
        Libérer les lots pré-réservés avant suppression."""
        for rec in self:
            # Vérifier les versements confirmés
            versements_confirmes = self.env['commercial.versement'].sudo().search([
                ('client_id', '=', rec.id),
                ('state', 'in', ('confirme', 'partiellement_rembourse')),
            ], limit=1)
            if versements_confirmes:
                raise UserError(
                    "Impossible de supprimer le contact « %s » car il a des versements confirmés." % rec.name
                )
            # Vérifier les échéances confirmées
            paiements = self.env['commercial.paiement'].sudo().search([('client_id', '=', rec.id)])
            for p in paiements:
                if (p.echeance_ids.filtered(lambda e: e.etat == 'paye')
                        or p.echeance_apport_ids.filtered(lambda e: e.etat == 'paye')):
                    raise UserError(
                        "Impossible de supprimer le contact « %s » car il a des paiements avec "
                        "des échéances confirmées." % rec.name
                    )
            # Libérer les lots pré-réservés
            for lot in rec.commercial_lot_ids.filtered(lambda l: l.state == 'en_option'):
                other_partners = self.env['res.partner'].search([
                    ('commercial_lot_ids', 'in', lot.id),
                    ('id', '!=', rec.id),
                ])
                if not other_partners:
                    lot.write({'state': 'disponible'})
        return super().unlink()

    commercial_user_id = fields.Many2one('res.users', string="Commercial",
                                        default=lambda self: self.env.user)
    has_confirmed_payment = fields.Boolean(
        string="A un paiement confirmé",
        compute='_compute_has_confirmed_payment')

    @api.depends(
        'commercial_lot_ids.versement_ids.state',
        'commercial_lot_ids.paiement_ids.echeance_ids.etat',
        'commercial_lot_ids.paiement_ids.echeance_apport_ids.etat',
    )
    def _compute_has_confirmed_payment(self):
        for rec in self:
            found = False
            for lot in rec.commercial_lot_ids:
                if rec._has_confirmed_paiement(lot):
                    found = True
                    break
                if lot.versement_ids.filtered(lambda v: v.state in ('confirme', 'partiellement_rembourse')):
                    found = True
                    break
            rec.has_confirmed_payment = found

    contact_category = fields.Selection(
        [('interne', 'Interne'), ('externe', 'Externe')],
        string='Catégorie de contact',
        default='externe',
    )

    # État civil
    genre = fields.Selection([
        ('homme', 'Homme'),
        ('femme', 'Femme'),
    ], string="Genre")
    date_naissance = fields.Date(string="Date de naissance")
    lieu_naissance = fields.Char(string="Lieu de naissance")
    acte_naissance = fields.Char(string="N° acte de naissance")
    pays_naissance_id = fields.Many2one('res.country', string="Pays de naissance")
    situation_familiale = fields.Selection([
        ('celibataire', 'Célibataire'),
        ('marie', 'Marié(e)'),
        ('divorce', 'Divorcé(e)'),
        ('veuf', 'Veuf/Veuve'),
    ], string="Situation familiale")

    # Source (nécessaire aussi sur res.partner pour la validation de vue)
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

    # Communications
    communication_ids = fields.One2many(
        'commercial.communication', 'partner_id', string="Communications")
    communication_count = fields.Integer(
        string="Nombre de communications",
        compute='_compute_communication_count')

    @api.depends('communication_ids')
    def _compute_communication_count(self):
        for rec in self:
            rec.communication_count = len(rec.communication_ids)

    def action_open_remise_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Remise',
            'res_model': 'commercial.remise.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.id},
        }

    def action_open_print_client_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Imprimer',
            'res_model': 'commercial.print.client.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.id},
        }

    def action_print_fiche_technique(self):
        return self.action_open_print_client_wizard()

    def action_open_print_situation_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Impression',
            'res_model': 'commercial.print.situation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.id},
        }

    def action_view_communications(self):
        self.ensure_one()
        wizard = self.env['commercial.communication.list.wizard'].create({
            'partner_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Communications',
            'res_model': 'commercial.communication.list.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }

    def action_view_reservation_parking(self):
        self.ensure_one()
        # Filtrer les lots de type parking du client
        parking_lots = self.commercial_lot_ids.filtered(
            lambda l: l.categorie_id and l.categorie_id.type_lot_id
            and 'PARK' in (l.categorie_id.type_lot_id.name or '').upper()
        )
        if not parking_lots:
            raise UserError(
                "Ce client n'a pas de lot de type Parking.\n"
                "Veuillez d'abord associer un lot de type Parking à ce client."
            )
        if len(parking_lots) == 1:
            # Un seul parking → ouvrir la fiche directement
            existing = self.env['commercial.reservation.parking'].search(
                [('client_id', '=', self.id), ('parking_id', '=', parking_lots.id)], limit=1)
            if not existing:
                existing = self.env['commercial.reservation.parking'].create({
                    'client_id': self.id,
                    'parking_id': parking_lots.id,
                })
            return {
                'type': 'ir.actions.act_window',
                'name': 'Fiche Parking',
                'res_model': 'commercial.reservation.parking',
                'view_mode': 'form',
                'res_id': existing.id,
                'context': {'default_client_id': self.id},
            }
        else:
            # Plusieurs parkings → wizard de sélection
            return {
                'type': 'ir.actions.act_window',
                'name': 'Sélectionner un parking',
                'res_model': 'commercial.select.parking.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_client_id': self.id},
            }

    # Documents
    document_ids = fields.One2many(
        'commercial.document.partner', 'partner_id', string="Documents")

    # Rappel - 1er Appel
    rappel_1_motif = fields.Char(string="Motif")
    rappel_1_date = fields.Date(string="Date")
    # Rappel - 2ème Appel
    rappel_2_motif = fields.Char(string="Motif")
    rappel_2_date = fields.Date(string="Date")
    # Rappel - 3ème Appel
    rappel_3_motif = fields.Char(string="Motif")
    rappel_3_date = fields.Date(string="Date")

    # Lots (Many2many pour sélection multiple)
    commercial_lot_ids = fields.Many2many('commercial.lot', string='Lots')
    # Lignes lot avec remise par contact
    partner_lot_line_ids = fields.One2many(
        'commercial.partner.lot', 'partner_id', string='Lignes Lots')
    # Historique des lots retirés (pré-réservés puis vendus/réservés par un autre)
    commercial_lot_history_ids = fields.Many2many(
        'commercial.lot', 'res_partner_commercial_lot_history_rel',
        'partner_id', 'lot_id',
        string='Historique des lots')
    lot_cards_html = fields.Html(
        string="Fiches Lots", compute='_compute_lot_cards_html', sanitize=False)
    contact_card_html = fields.Html(
        string="Carte Contact", compute='_compute_contact_card_html', sanitize=False)
    montant_global_lots = fields.Float(
        string="Montant global", compute='_compute_totaux_lots')
    montant_paye_global = fields.Float(
        string="Montant payé global", compute='_compute_totaux_lots')
    reste_global = fields.Float(
        string="Reste global", compute='_compute_totaux_lots')

    def _get_lot_remise(self, lot):
        """Return the partner-specific remise for a lot."""
        line = self.env['commercial.partner.lot'].search([
            ('partner_id', '=', self.id),
            ('lot_id', '=', lot.id),
        ], limit=1)
        return line.remise if line else 0.0

    def _get_lot_montant_paye(self, lot):
        """Calcule le montant payé pour un lot :
        - versements confirmés (montant)
        - versements partiellement remboursés (montant_restant)
        - échéances paiement confirmées
        - échéances apport confirmées
        """
        montant = 0.0
        for v in lot.versement_ids:
            if v.state == 'confirme':
                montant += v.montant
            elif v.state == 'partiellement_rembourse':
                montant += v.montant_restant
        for p in lot.paiement_ids:
            montant += sum(e.montant for e in p.echeance_ids if e.etat == 'paye')
            montant += sum(e.montant for e in p.echeance_apport_ids if e.etat == 'paye')
        return montant

    @api.depends(
        'commercial_lot_ids.montant_global',
        'partner_lot_line_ids.remise',
        'commercial_lot_ids.versement_ids.montant',
        'commercial_lot_ids.versement_ids.state',
        'commercial_lot_ids.versement_ids.montant_restant',
        'commercial_lot_ids.paiement_ids.echeance_ids.montant',
        'commercial_lot_ids.paiement_ids.echeance_ids.etat',
        'commercial_lot_ids.paiement_ids.echeance_apport_ids.montant',
        'commercial_lot_ids.paiement_ids.echeance_apport_ids.etat',
    )
    def _compute_totaux_lots(self):
        for rec in self:
            montant_total = 0.0
            montant_paye = 0.0
            for lot in rec.commercial_lot_ids:
                remise = rec._get_lot_remise(lot)
                net = lot.montant_global - remise
                montant_total += net
                montant_paye += rec._get_lot_montant_paye(lot)
            rec.montant_global_lots = montant_total
            rec.montant_paye_global = montant_paye
            rec.reste_global = montant_total - montant_paye

    @api.depends('name', 'phone', 'mobile', 'commercial_lot_ids',
                 'montant_global_lots', 'montant_paye_global', 'reste_global')
    def _compute_contact_card_html(self):
        def fmt(val):
            return '{:,.2f}'.format(val).replace(',', ' ')
        for rec in self:
            nom = rec.name or ''
            tel = rec.phone or rec.mobile or ''
            rec.contact_card_html = '''
            <div style="text-align:right;padding:4px 0;">
                <div style="font-size:18px;font-weight:700;color:#333;">%(nom)s</div>
                <div style="font-size:13px;color:#666;margin-top:2px;">%(tel)s</div>
                %(totaux)s
            </div>
            ''' % {
                'nom': nom,
                'tel': tel if tel else '',
                'totaux': '''
                <div style="display:flex;gap:20px;justify-content:flex-end;
                            margin-top:8px;font-size:11px;">
                    <div>
                        <span style="color:#888;">Montant global</span><br/>
                        <span style="font-weight:700;color:#4E4E4E;">%s DA</span>
                    </div>
                    <div>
                        <span style="color:#888;">Montant payé</span><br/>
                        <span style="font-weight:700;color:#27AE60;">%s DA</span>
                    </div>
                    <div>
                        <span style="color:#888;">Reste</span><br/>
                        <span style="font-weight:700;color:#F39C12;">%s DA</span>
                    </div>
                </div>''' % (fmt(rec.montant_global_lots), fmt(rec.montant_paye_global), fmt(rec.reste_global))
                if rec.commercial_lot_ids else '',
            }
    commercial_lot_projet_ids = fields.Many2many(
        'commercial.projet', string='Projet',
        compute='_compute_commercial_lot_projet_ids')
    commercial_lot_bloc_ids = fields.Many2many(
        'commercial.bloc', string='Bloc',
        compute='_compute_commercial_lot_bloc_ids')

    # Anciens champs (conservés pour compatibilité base de données)
    commercial_projet_id = fields.Many2one('commercial.projet', string='Projet', ondelete='set null')
    commercial_bloc_id = fields.Many2one('commercial.bloc', string='Bloc', ondelete='set null')
    commercial_etage_id = fields.Many2one('commercial.etage', string='Étage', ondelete='set null')
    commercial_lot_state_filter = fields.Selection([
        ('disponible', 'Disponible'),
        ('en_option', 'Pré-réservé'),
        ('reserve', 'Réservé'),
        ('vendu', 'Vendu'),
    ], string="Filtre statut lot", store=False)
    commercial_lot_id = fields.Many2one('commercial.lot', string='Lot', ondelete='set null')

    @api.depends('commercial_lot_ids.projet_id')
    def _compute_commercial_lot_projet_ids(self):
        for rec in self:
            rec.commercial_lot_projet_ids = rec.commercial_lot_ids.mapped('projet_id')

    @api.depends('commercial_lot_ids.bloc_id')
    def _compute_commercial_lot_bloc_ids(self):
        for rec in self:
            rec.commercial_lot_bloc_ids = rec.commercial_lot_ids.mapped('bloc_id')

    @api.depends(
        'commercial_lot_ids',
        'commercial_lot_ids.montant_global',
        'partner_lot_line_ids.remise',
        'commercial_lot_ids.projet_id',
        'commercial_lot_ids.bloc_id',
        'commercial_lot_ids.etage_id',
        'commercial_lot_ids.versement_ids.montant',
        'commercial_lot_ids.versement_ids.state',
        'commercial_lot_ids.versement_ids.montant_restant',
        'commercial_lot_ids.paiement_ids.echeance_ids.montant',
        'commercial_lot_ids.paiement_ids.echeance_ids.etat',
        'commercial_lot_ids.paiement_ids.echeance_apport_ids.montant',
        'commercial_lot_ids.paiement_ids.echeance_apport_ids.etat',
    )
    def _compute_lot_cards_html(self):
        for rec in self:
            if not rec.commercial_lot_ids:
                rec.lot_cards_html = False
                continue
            cards = []
            for lot in rec.commercial_lot_ids:
                remise = rec._get_lot_remise(lot)
                montant_net = lot.montant_global - remise
                montant_paye = rec._get_lot_montant_paye(lot)
                reste = montant_net - montant_paye

                projet_name = lot.projet_id.name or ''
                bloc_name = lot.bloc_id.code or ''
                etage_name = lot.etage_id.name or ''
                lot_num = lot.numero_lot or ''

                def fmt(val):
                    return '{:,.2f}'.format(val).replace(',', ' ')

                cards.append('''
                <div style="flex:1;min-width:280px;max-width:420px;
                            border:1px solid #dee2e6;border-radius:0;
                            overflow:hidden;background:#f8f9fa;">
                    <div style="padding:8px 14px;font-size:12px;font-weight:700;
                                color:#333;border-bottom:1px solid #dee2e6;">
                        %(projet)s &nbsp;|&nbsp; Lot %(lot)s &nbsp;|&nbsp; %(etage)s &nbsp;|&nbsp; Bloc %(bloc)s
                    </div>
                    <div style="padding:10px 14px;font-size:10pt;">
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                            <span style="color:#555555;">Montant total</span>
                            <span style="font-weight:700;color:#4E4E4E;">%(montant_total)s DA</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                            <span style="color:#555555;">Remise</span>
                            <span style="font-weight:700;color:#E74C3C;">%(remise)s DA</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                            <span style="color:#555555;">Montant payé</span>
                            <span style="font-weight:700;color:#27AE60;">%(montant_paye)s DA</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                            <span style="color:#555555;">Reste</span>
                            <span style="font-weight:700;color:#F39C12;">%(reste)s DA</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-top:8px;
                                    padding-top:6px;border-top:1px solid #999;">
                            <span style="font-weight:700;color:#333333;">Montant net client</span>
                            <span style="font-weight:700;color:#2C3E50;">%(montant_net)s DA</span>
                        </div>
                    </div>
                </div>
                ''' % {
                    'projet': projet_name,
                    'lot': lot_num,
                    'etage': etage_name,
                    'bloc': bloc_name,
                    'montant_total': fmt(lot.montant_global),
                    'remise': fmt(remise),
                    'montant_paye': fmt(montant_paye),
                    'reste': fmt(reste),
                    'montant_net': fmt(montant_net),
                })
            rec.lot_cards_html = (
                '<div style="display:flex;flex-wrap:wrap;gap:14px;'
                'margin-bottom:16px;padding:8px 0;">'
                + ''.join(cards)
                + '</div>'
            )

    @api.onchange('commercial_lot_ids')
    def _onchange_commercial_lot_ids(self):
        """Bloque uniquement les nouveaux lots vendus ou réservés par un autre client."""
        existing_ids = set()
        if self._origin and self._origin.id:
            existing_ids = set(
                self.env['res.partner'].browse(self._origin.id).commercial_lot_ids.ids)
        new_lots = self.commercial_lot_ids.filtered(
            lambda l: l.id and l.id not in existing_ids)
        blocked = new_lots.filtered(lambda l: l.state in ('vendu', 'reserve'))
        if blocked:
            names = ', '.join(
                "%s (%s)" % (l.numero_lot, dict(l._fields['state'].selection).get(l.state))
                for l in blocked
            )
            self.commercial_lot_ids -= blocked
            return {
                'warning': {
                    'title': "Sélection interdite",
                    'message': "Impossible de sélectionner les lots suivants :\n%s\n"
                               "Seuls les lots disponibles ou pré-réservés peuvent être sélectionnés." % names,
                }
            }

    def _has_confirmed_paiement(self, lot):
        """Check if a lot has any écheance paid."""
        paiements = self.env['commercial.paiement'].search([('lot_id', '=', lot.id)])
        for p in paiements:
            if any(e.etat == 'paye' for e in p.echeance_ids) or \
               any(e.etat == 'paye' for e in p.echeance_apport_ids):
                return True
        return False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        PartnerLot = self.env['commercial.partner.lot']
        for record in records:
            if record.commercial_lot_ids:
                record.commercial_lot_ids.filtered(
                    lambda l: l.state == 'disponible'
                ).write({'state': 'en_option'})
                # Create partner_lot lines for initial lots (skip if already created via One2many)
                for lot in record.commercial_lot_ids:
                    if not PartnerLot.search([
                        ('partner_id', '=', record.id),
                        ('lot_id', '=', lot.id),
                    ], limit=1):
                        PartnerLot.with_context(skip_lot_sync=True).create({
                            'partner_id': record.id,
                            'lot_id': lot.id,
                        })
        return records

    def write(self, vals):
        # Lock type when set to 'client'
        if vals.get('type_client_commercial') == 'client':
            vals['is_type_client_locked'] = True
        # Auto-set commercial_projet_id when becoming client
        if 'type_client_commercial' in vals and vals['type_client_commercial'] == 'client':
            for record in self:
                if not record.commercial_projet_id and record.commercial_lot_ids:
                    projet = record.commercial_lot_ids[:1].mapped('projet_id')
                    if projet:
                        record.commercial_projet_id = projet

        # Handle lot assignment changes
        if 'commercial_lot_ids' in vals:
            old_lot_ids_map = {rec.id: set(rec.commercial_lot_ids.ids) for rec in self}
            res = super().write(vals)
            self.env.invalidate_all()
            PartnerLot = self.env['commercial.partner.lot']
            for record in self:
                lots_to_update = record.commercial_lot_ids.filtered(lambda l: l.state == 'disponible')
                if lots_to_update:
                    lots_to_update.write({'state': 'en_option'})
                # Sync partner_lot_line_ids with commercial_lot_ids
                old_ids = old_lot_ids_map.get(record.id, set())
                new_ids = set(record.commercial_lot_ids.ids)
                added_ids = new_ids - old_ids
                removed_ids = old_ids - new_ids
                if not self.env.context.get('skip_lot_sync'):
                    # Create lines for newly added lots
                    for lot_id in added_ids:
                        if not PartnerLot.search([
                            ('partner_id', '=', record.id),
                            ('lot_id', '=', lot_id),
                        ], limit=1):
                            PartnerLot.with_context(skip_lot_sync=True).create({
                                'partner_id': record.id,
                                'lot_id': lot_id,
                            })
                    # Remove lines for removed lots
                    if removed_ids:
                        PartnerLot.with_context(skip_lot_sync=True).search([
                            ('partner_id', '=', record.id),
                            ('lot_id', 'in', list(removed_ids)),
                        ]).unlink()
                # Bloquer la suppression des lots réservés ou vendus (sauf blocage contact)
                if removed_ids and not self.env.context.get('force_lot_release'):
                    removed_lots = self.env['commercial.lot'].browse(list(removed_ids))
                    blocked_lots = removed_lots.filtered(lambda l: l.state in ('reserve', 'vendu'))
                    if blocked_lots:
                        names = ', '.join(
                            "%s (%s)" % (l.numero_lot, dict(l._fields['state'].selection).get(l.state))
                            for l in blocked_lots
                        )
                        raise UserError(
                            "Impossible de retirer les lots suivants car ils sont réservés ou vendus :\n%s" % names)
                # Handle removed lots state
                if removed_ids:
                    removed_lots = self.env['commercial.lot'].browse(list(removed_ids))
                    for lot in removed_lots:
                        if not self._has_confirmed_paiement(lot):
                            if lot.state == 'en_option':
                                other_partners = self.env['res.partner'].search([
                                    ('commercial_lot_ids', 'in', lot.id),
                                    ('id', '!=', record.id),
                                ])
                                if other_partners:
                                    lot.write({'state': 'en_option'})
                                else:
                                    lot.write({'state': 'disponible'})
            return res
        return super().write(vals)

    def _update_lot_states(self):
        """Set available lots to pre-reserved when assigned to a contact."""
        for record in self:
            lots = record.commercial_lot_ids.filtered(lambda l: l.state == 'disponible')
            if lots:
                lots.write({'state': 'en_option'})

    # Décision
    type_client_commercial = fields.Selection(
        [('Visiteur', 'Visiteur'),
         ('client', 'Client')],
        string="Type client commercial",
        default='Visiteur',
    )
    type_client_autre = fields.Char(string="Autre (préciser)")
    is_type_client_locked = fields.Boolean(default=False)
    is_blocked = fields.Boolean(string="Bloqué", default=False)
    blocked_display = fields.Html(
        string=" ", compute='_compute_blocked_display', sanitize=False)

    @api.depends('is_blocked')
    def _compute_blocked_display(self):
        for rec in self:
            if rec.is_blocked:
                rec.blocked_display = '<i class="fa fa-ban" style="color: red; font-size: 1.2em;" title="Bloqué"></i>'
            else:
                rec.blocked_display = False

    def action_dummy(self):
        return

    def action_add_lot(self):
        self.ensure_one()
        wizard = self.env['commercial.add.lot.wizard'].create({
            'partner_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ajouter des lots',
            'res_model': 'commercial.add.lot.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }

    def action_set_blocked(self):
        self.ensure_one()
        all_lots = self.commercial_lot_ids
        if all_lots:
            # Sauvegarder l'ancien état de chaque lot
            lot_states = {lot.id: lot.state for lot in all_lots}
            # Retirer tous les lots du contact (force_lot_release pour bypass la protection reserve/vendu)
            self.with_context(skip_lot_sync=True, force_lot_release=True).write({
                'commercial_lot_ids': [(5, 0, 0)],
            })
            # Ajouter à l'historique
            self.write({
                'commercial_lot_history_ids': [(4, lot.id) for lot in all_lots],
            })
            # Supprimer les lignes partner_lot correspondantes
            self.env['commercial.partner.lot'].search([
                ('partner_id', '=', self.id),
                ('lot_id', 'in', all_lots.ids),
            ]).with_context(skip_lot_sync=True).unlink()
            # Mettre à jour le statut de chaque lot libéré
            for lot in all_lots:
                old_state = lot_states[lot.id]
                if old_state in ('reserve', 'vendu'):
                    # Lots réservés/vendus → disponible directement
                    lot.write({'state': 'disponible'})
                elif old_state == 'en_option':
                    # Lots pré-réservés → disponible sauf si un autre contact non-bloqué l'a
                    other_partners = self.env['res.partner'].search([
                        ('commercial_lot_ids', 'in', lot.id),
                        ('id', '!=', self.id),
                        ('is_blocked', '=', False),
                    ])
                    if other_partners:
                        lot.write({'state': 'en_option'})
                    else:
                        lot.write({'state': 'disponible'})
        self.write({'is_blocked': True})

    def action_set_unblocked(self):
        self.ensure_one()
        self.write({'is_blocked': False})

    def action_set_visiteur(self):
        self.ensure_one()
        self.write({'type_client_commercial': 'Visiteur'})

    def action_set_client(self):
        self.ensure_one()
        self.write({'type_client_commercial': 'client'})

    def action_add_document(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ajouter un document',
            'res_model': 'commercial.document.partner',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.id,
            },
        }

    def action_add_communication(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ajouter une communication',
            'res_model': 'commercial.communication',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.id,
            },
        }

    def action_open_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'res.partner',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
            'context': {
                'default_contact_category': 'interne',
                'is_contact_externe': True,
            },
        }

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        res = super().read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
        if groupby and groupby[0] == 'type_client_commercial':
            res.sort(key=lambda r: TYPE_CLIENT_ORDER.get(r.get('type_client_commercial'), 99))
        return res
