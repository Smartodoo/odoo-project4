from datetime import timedelta

from dateutil.relativedelta import relativedelta

from num2words import num2words

from odoo import models, fields, api
from odoo.exceptions import UserError


class CommercialLocation(models.Model):
    _name = 'commercial.location'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Contrat de Location'
    _rec_name = 'name'

    name = fields.Char(
        string="Référence", readonly=True, copy=False, default='Nouveau')

    lot_id = fields.Many2one(
        'commercial.lot', string="Lot", ondelete='cascade', tracking=True)
    projet_id = fields.Many2one(
        related='lot_id.projet_id', string="Projet", store=True, readonly=True)
    bloc_id = fields.Many2one(
        related='lot_id.bloc_id', string="Bloc", store=True, readonly=True)
    etage_id = fields.Many2one(
        related='lot_id.etage_id', string="Étage", store=True, readonly=True)
    client_location_id = fields.Many2one(
        'commercial.client.location', string="Raison sociale", tracking=True)

    type_contrat = fields.Selection([
        ('mensuel', 'Mensuel'),
        ('annuel', 'Annuel'),
    ], string="Type de contrat", default='mensuel', tracking=True)

    date_debut = fields.Date(string="Date début", tracking=True)
    date_fin = fields.Date(
        string="Date fin", compute='_compute_date_fin', store=True, readonly=False)

    state = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
        ('annule', 'Annulé'),
    ], string="Statut", compute='_compute_state', store=True, tracking=True)

    is_annule = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

    delais = fields.Integer(string="Délais (mois)", tracking=True)
    delais_annees = fields.Integer(string="Délais (années)", tracking=True)
    montant_mensuel = fields.Float(string="Montant mensuel", tracking=True)
    montant_declare = fields.Float(string="Déclaré", tracking=True)
    caution_garantie = fields.Float(string="Caution de garantie", tracking=True)
    montant_annuel = fields.Float(
        string="Montant annuel", compute='_compute_montant_annuel', store=True)
    montant_g50 = fields.Float(
        string="Montant G51", compute='_compute_montant_g50', store=True)
    net_encaisse = fields.Float(
        string="Net encaissé", compute='_compute_net_encaisse', store=True)
    recuperation_ids = fields.One2many(
        'commercial.recuperation', 'location_id', string="Récupérations")
    recuperation_nom_1 = fields.Char(
        string="Récup. 1", compute='_compute_recuperation_colonnes', store=True)
    recuperation_montant_1 = fields.Float(
        string="Montant récup. 1", compute='_compute_recuperation_colonnes', store=True)
    recuperation_nom_2 = fields.Char(
        string="Récup. 2", compute='_compute_recuperation_colonnes', store=True)
    recuperation_montant_2 = fields.Float(
        string="Montant récup. 2", compute='_compute_recuperation_colonnes', store=True)

    # --- Versements location ---
    versement_location_ids = fields.One2many(
        'commercial.versement.location', 'location_id', string="Versements")
    total_versements = fields.Float(
        string="Versement", compute='_compute_versements', store=True)
    nombre_versements = fields.Integer(
        string="Nombre de versements", compute='_compute_versements', store=True)
    reste_a_payer = fields.Float(
        string="Reste à payer", compute='_compute_reste_a_payer', store=True)

    annee = fields.Char(
        string="Année", compute='_compute_annee', store=True)

    notif_1mois_envoyee = fields.Boolean(default=False)
    notif_15j_envoyee = fields.Boolean(default=False)

    company_id = fields.Many2one(
        'res.company', string="Société", default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'commercial.location') or 'Nouveau'
            if not vals.get('recuperation_ids'):
                vals['recuperation_ids'] = [
                    (0, 0, {}),
                    (0, 0, {}),
                ]
            if vals.get('type_contrat') == 'annuel' and vals.get('delais_annees'):
                vals['delais'] = vals['delais_annees'] * 12
        return super().create(vals_list)

    def write(self, vals):
        # Champs autorisés à être mis à jour (champs calculés / système)
        computed_fields = {'state', 'date_fin', 'montant_annuel', 'montant_g50',
                          'net_encaisse', 'total_versements', 'nombre_versements',
                          'reste_a_payer', 'annee', 'recuperation_nom_1',
                          'recuperation_montant_1', 'recuperation_nom_2',
                          'recuperation_montant_2', 'message_main_attachment_id',
                          'delais', 'delais_annees', 'notif_1mois_envoyee', 'notif_15j_envoyee',
                          'is_annule', 'active'}
        if set(vals.keys()) - computed_fields:
            for rec in self:
                if rec.state == 'termine':
                    raise UserError("Impossible de modifier un contrat terminé.")
                if rec.state == 'en_cours':
                    raise UserError("Impossible de modifier un contrat en cours.")
                if rec.state == 'annule':
                    raise UserError("Impossible de modifier un contrat annulé.")
        res = super().write(vals)
        if 'delais_annees' in vals or 'type_contrat' in vals:
            for rec in self:
                if rec.type_contrat == 'annuel' and rec.delais_annees:
                    super(CommercialLocation, rec).write({'delais': rec.delais_annees * 12})
        return res

    @api.depends('montant_mensuel', 'delais', 'delais_annees', 'type_contrat')
    def _compute_montant_annuel(self):
        for rec in self:
            if rec.type_contrat == 'annuel':
                rec.montant_annuel = rec.montant_mensuel * (rec.delais_annees or 0) * 12
            else:
                rec.montant_annuel = rec.montant_mensuel * (rec.delais or 0)

    @api.depends('montant_annuel', 'montant_g50')
    def _compute_net_encaisse(self):
        for rec in self:
            rec.net_encaisse = rec.montant_annuel - rec.montant_g50

    @api.depends('recuperation_ids.responsable_id', 'recuperation_ids.montant')
    def _compute_recuperation_colonnes(self):
        for rec in self:
            lines = rec.recuperation_ids.sorted('id')
            if len(lines) >= 1:
                rec.recuperation_nom_1 = lines[0].responsable_id.name or ''
                rec.recuperation_montant_1 = lines[0].montant
            else:
                rec.recuperation_nom_1 = ''
                rec.recuperation_montant_1 = 0
            if len(lines) >= 2:
                rec.recuperation_nom_2 = lines[1].responsable_id.name or ''
                rec.recuperation_montant_2 = lines[1].montant
            else:
                rec.recuperation_nom_2 = ''
                rec.recuperation_montant_2 = 0

    @api.depends('montant_declare', 'delais', 'delais_annees', 'type_contrat')
    def _compute_montant_g50(self):
        for rec in self:
            if rec.type_contrat == 'annuel':
                rec.montant_g50 = rec.montant_declare * (rec.delais_annees or 0) * 12 * 0.15
            else:
                rec.montant_g50 = rec.montant_declare * (rec.delais or 0) * 0.15

    @api.depends('versement_location_ids.montant', 'versement_location_ids.state')
    def _compute_versements(self):
        for rec in self:
            confirmed = rec.versement_location_ids.filtered(
                lambda v: v.state == 'confirme')
            rec.total_versements = sum(confirmed.mapped('montant'))
            rec.nombre_versements = len(confirmed)

    @api.depends('versement_location_ids.state', 'date_fin', 'is_annule')
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.is_annule:
                rec.state = 'annule'
                continue
            all_versements = rec.versement_location_ids
            if rec.date_fin and rec.date_fin <= today:
                rec.state = 'termine'
            elif not all_versements:
                rec.state = 'brouillon'
            else:
                confirmed = all_versements.filtered(lambda v: v.state == 'confirme')
                if confirmed:
                    rec.state = 'en_cours'
                else:
                    rec.state = 'brouillon'

    @api.depends('montant_annuel', 'total_versements')
    def _compute_reste_a_payer(self):
        for rec in self:
            rec.reste_a_payer = rec.montant_annuel - rec.total_versements

    @api.constrains('lot_id')
    def _check_lot_reserve(self):
        for rec in self:
            if rec.lot_id:
                other_contrats = self.env['commercial.location'].search([
                    ('lot_id', '=', rec.lot_id.id),
                    ('id', '!=', rec.id),
                    ('state', '!=', 'termine'),
                ])
                for contrat in other_contrats:
                    all_v = contrat.versement_location_ids
                    if all_v:
                        confirmed = all_v.filtered(lambda v: v.state == 'confirme')
                        if confirmed and len(confirmed) < len(all_v):
                            nom_client = contrat.client_location_id.display_name or ''
                            raise UserError(
                                "Le lot '%s' est déjà réservé par le client '%s' (contrat %s). "
                                "Veuillez choisir un autre lot."
                                % (rec.lot_id.numero_lot, nom_client, contrat.name)
                            )

    def unlink(self):
        for rec in self:
            if rec.state != 'brouillon':
                raise UserError(
                    "Impossible de supprimer le contrat '%s', archiver à la place. "
                    "Seuls les contrats en brouillon peuvent être supprimés."
                    % rec.name)
        return super().unlink()

    def action_open_decharge_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Imprimer une décharge de versement',
            'res_model': 'commercial.print.decharge.location.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_location_id': self.id},
        }

    def action_annuler(self):
        for rec in self:
            if rec.state != 'en_cours':
                raise UserError("Seul un contrat en cours peut être annulé.")
            # Remettre le lot en disponible
            if rec.lot_id:
                rec.lot_id.sudo().write({'state': 'disponible'})
            rec.sudo().write({'is_annule': True})

    def action_archive(self):
        for rec in self:
            if rec.state not in ('annule', 'termine'):
                raise UserError(
                    "Impossible d'archiver le contrat '%s'. "
                    "Seuls les contrats annulés ou terminés peuvent être archivés."
                    % rec.name)
        return super().action_archive()

    def get_montant_en_lettres(self):
        self.ensure_one()
        partie_entiere = int(self.caution_garantie)
        partie_decimale = round((self.caution_garantie - partie_entiere) * 100)
        resultat = num2words(partie_entiere, lang='fr').upper() + " DINARS"
        if partie_decimale:
            resultat += " ET " + num2words(partie_decimale, lang='fr').upper() + " CENTIMES"
        return resultat

    @api.onchange('delais_annees', 'type_contrat')
    def _onchange_delais_annees(self):
        if self.type_contrat == 'annuel' and self.delais_annees:
            self.delais = self.delais_annees * 12

    @api.depends('date_debut', 'delais', 'delais_annees', 'type_contrat')
    def _compute_date_fin(self):
        for rec in self:
            if rec.date_debut:
                if rec.type_contrat == 'annuel' and rec.delais_annees and rec.delais_annees > 0:
                    rec.date_fin = rec.date_debut + relativedelta(months=rec.delais_annees * 12)
                elif rec.type_contrat == 'mensuel' and rec.delais and rec.delais > 0:
                    rec.date_fin = rec.date_debut + relativedelta(months=rec.delais)
                else:
                    rec.date_fin = False
            else:
                rec.date_fin = False

    @api.depends('date_debut')
    def _compute_annee(self):
        for rec in self:
            rec.annee = str(rec.date_debut.year) if rec.date_debut else ''

    def action_open_location_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Contrat de Location',
            'res_model': 'commercial.location',
            'view_mode': 'form',
            'res_id': self.id,
        }

    @api.model
    def check_upcoming_liberations(self):
        """Notifier 1 mois et 15 jours avant la fin d'un contrat de location."""
        today = fields.Date.today()
        target_30 = today + timedelta(days=30)
        target_15 = today + timedelta(days=15)

        # Contrats en cours dont date_fin <= 30 jours, pas encore notifiés 1 mois
        contrats_1mois = self.search([
            ('state', '=', 'en_cours'),
            ('date_fin', '<=', target_30),
            ('date_fin', '>=', today),
            ('notif_1mois_envoyee', '=', False),
        ])
        # Contrats en cours dont date_fin <= 15 jours, pas encore notifiés 15j
        contrats_15j = self.search([
            ('state', '=', 'en_cours'),
            ('date_fin', '<=', target_15),
            ('date_fin', '>=', today),
            ('notif_15j_envoyee', '=', False),
        ])

        a_notifier = []
        for c in contrats_1mois:
            a_notifier.append((c, '1mois'))
        for c in contrats_15j:
            a_notifier.append((c, '15j'))

        if not a_notifier:
            return

        # Créer / récupérer le canal Discuss
        Channel = self.env['discuss.channel']
        channel = Channel.sudo().search([('name', '=', 'Libération des Lots')], limit=1)
        if not channel:
            channel = Channel.sudo().create({
                'name': 'Libération des Lots',
                'channel_type': 'channel',
            })

        # Ajouter tous les utilisateurs internes au canal
        internal_group = self.env.ref('base.group_user')
        all_partners = internal_group.users.mapped('partner_id')
        existing_partner_ids = channel.sudo().channel_member_ids.mapped('partner_id').ids
        new_partner_ids = [p.id for p in all_partners if p.id not in existing_partner_ids]
        if new_partner_ids:
            channel.sudo().add_members(partner_ids=new_partner_ids)

        author_partner = self.env.ref('mail_bot.partner_odoo_bot', raise_if_not_found=False) \
                         or self.env.ref('base.partner_root')

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''

        for contrat, notif_type in a_notifier:
            delai = "1 mois" if notif_type == '1mois' else "15 jours"
            record_url = f"{base_url}/web#id={contrat.id}&model=commercial.location&view_type=form"
            html_message = f"""
                <p><b>Libération de lot dans {delai} :</b></p>
                <p>Contrat : <b>{contrat.name or ''}</b></p>
                <p>Lot : <b>{contrat.lot_id.numero_lot or ''}</b> — Projet : <b>{contrat.projet_id.name or ''}</b></p>
                <p>Client : <b>{contrat.client_location_id.display_name or ''}</b></p>
                <p>Date fin : <b>{contrat.date_fin}</b></p>
                <p><a href="{record_url}" target="_blank" rel="noopener">Ouvrir le contrat</a></p>
            """
            channel.sudo().message_post(
                author_id=author_partner.id,
                body=html_message,
                body_is_html=True,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=all_partners.ids,
            )
            if notif_type == '1mois':
                contrat.sudo().write({'notif_1mois_envoyee': True})
            else:
                contrat.sudo().write({'notif_15j_envoyee': True})

        return True

    def action_preview_report_multi(self):
        """Prévisualiser le rapport pour plusieurs enregistrements sélectionnés"""
        if not self:
            raise UserError("Veuillez sélectionner au moins un enregistrement.")
        ids_str = ','.join(str(rec.id) for rec in self)
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/commercial.report_recap_location_template/%s' % ids_str,
            'target': 'new',
        }

    def action_generer_versements(self):
        for rec in self:
            if not rec.date_debut:
                raise UserError("Veuillez renseigner la date de début.")
            if not rec.montant_mensuel:
                raise UserError("Veuillez renseigner le montant mensuel.")
            # Supprimer les anciens versements brouillon
            rec.versement_location_ids.filtered(
                lambda v: v.state == 'brouillon').unlink()
            if rec.type_contrat == 'mensuel':
                if not rec.delais or rec.delais <= 0:
                    raise UserError("Veuillez renseigner le délais (nombre de mois).")
                # Mensuel : 1 seul versement avec le montant net_encaissé
                self.env['commercial.versement.location'].create({
                    'location_id': rec.id,
                    'montant': rec.net_encaisse,
                    'date': rec.date_debut,
                })
            else:
                # Annuel : N versements (1 par année), espacés de 12 mois
                if not rec.delais_annees or rec.delais_annees <= 0:
                    raise UserError("Veuillez renseigner le délais (nombre d'années).")
                montant_par_annee = rec.net_encaisse / rec.delais_annees
                for i in range(rec.delais_annees):
                    date_versement = rec.date_debut + relativedelta(months=i * 12)
                    self.env['commercial.versement.location'].create({
                        'location_id': rec.id,
                        'montant': montant_par_annee,
                        'date': date_versement,
                    })

