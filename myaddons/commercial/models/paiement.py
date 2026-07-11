from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


def _notify_admin_echeance(rec, label, page):
    """Envoie une notification aux admins commercial pour une échéance brouillon."""
    env = rec.env
    admin_group = env.ref('commercial.group_commercial_admin', raise_if_not_found=False)
    if not admin_group:
        return
    Channel = env['discuss.channel']
    channel = Channel.sudo().search([('name', '=', 'Validation Versements & Paiements')], limit=1)
    if not channel:
        channel = Channel.sudo().create({
            'name': 'Validation Versements & Paiements',
            'channel_type': 'channel',
            'group_public_id': admin_group.id,
        })
    admin_partners = admin_group.users.mapped('partner_id')
    existing_ids = channel.sudo().channel_partner_ids.ids
    for partner in admin_partners:
        if partner.id not in existing_ids:
            channel.sudo().write({'channel_partner_ids': [(4, partner.id)]})
    author = env.ref('base.partner_root')
    base_url = env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
    paiement = rec.paiement_id
    url = f"{base_url}/web#id={paiement.id}&model=commercial.paiement&view_type=form"
    html = f"""
        <div style="background: #dbeafe; border: 1px solid #93c5fd; border-left: 5px solid #2563eb; border-radius: 10px; padding: 18px 22px; margin: 8px 0; box-shadow: 0 2px 8px rgba(37,99,235,0.10);">
            <div style="display: flex; align-items: center; margin-bottom: 14px;">
                <span style="background: #1d4ed8; color: #ffffff; font-size: 13px; font-weight: 700; padding: 4px 12px; border-radius: 20px; letter-spacing: 0.3px;">{label}</span>
            </div>
            <table style="width: 100%; font-size: 13px; color: #1e3a5f; border-collapse: collapse;">
                <tr><td style="padding: 6px 0; width: 120px; color: #3b82f6; font-weight: 500;">Client</td><td style="padding: 6px 0; font-weight: 600; color: #1e3a5f;">{paiement.client_id.name or ''}</td></tr>
                <tr><td style="padding: 6px 0; color: #3b82f6; font-weight: 500;">Lot</td><td style="padding: 6px 0; font-weight: 600; color: #1e3a5f;">{paiement.lot_id.numero_lot or ''} <span style="color: #60a5fa;">—</span> Projet : {paiement.lot_id.projet_id.name or ''}</td></tr>
                <tr><td style="padding: 6px 0; color: #3b82f6; font-weight: 500;">Échéance N°</td><td style="padding: 6px 0; font-weight: 600; color: #1e3a5f;">{rec.numero} <span style="color: #60a5fa;">—</span> Onglet : {page}</td></tr>
                <tr><td style="padding: 6px 0; color: #3b82f6; font-weight: 500;">Montant</td><td style="padding: 6px 0; font-weight: 700; color: #1d4ed8; font-size: 14px;">{rec.montant:,.2f}</td></tr>
                <tr><td style="padding: 6px 0; color: #3b82f6; font-weight: 500;">Créé par</td><td style="padding: 6px 0; font-weight: 600; color: #1e3a5f;">{env.user.name}</td></tr>
            </table>
            <div style="margin-top: 14px; padding-top: 12px; border-top: 1px solid #93c5fd;">
                <a href="{url}" style="display: inline-block; background: #1d4ed8; color: #ffffff; padding: 8px 20px; border-radius: 6px; font-size: 13px; font-weight: 600; text-decoration: none;">Ouvrir la fiche paiement &rarr;</a>
            </div>
        </div>
    """
    message = channel.sudo().message_post(
        author_id=author.id,
        body=html, body_is_html=True,
        message_type='comment',
        subtype_xmlid='mail.mt_comment',
        partner_ids=admin_partners.ids,
    )
    rec.notified = True
    return message


def _mark_notification_done(rec):
    """Marque la notification Discuss comme traitée et reposte un résumé si nécessaire."""
    if not rec.notification_message_id:
        return
    msg = rec.notification_message_id.sudo()
    body = msg.body or ''
    import re
    # Supprimer le bouton/lien cliquable
    body = re.sub(r'<div[^>]*border-top[^>]*>.*?</div>', '', body, flags=re.DOTALL)
    body = re.sub(r'<p[^>]*>\s*<a [^>]*>.*?</a>\s*</p>', '', body)
    # Remplacer le style bleu par un style gris (fond + bordures + textes)
    body = body.replace('background: #dbeafe', 'background: #f1f5f9')
    body = body.replace('border: 1px solid #93c5fd', 'border: 1px solid #e2e8f0')
    body = body.replace('border-left: 5px solid #2563eb', 'border-left: 5px solid #cbd5e1')
    body = body.replace('box-shadow: 0 2px 8px rgba(37,99,235,0.10)', 'box-shadow: none')
    body = body.replace('background: #1d4ed8; color: #ffffff', 'background: #94a3b8; color: #ffffff')
    body = body.replace('color: #1e3a5f', 'color: #94a3b8')
    body = body.replace('color: #3b82f6', 'color: #94a3b8')
    body = body.replace('color: #1d4ed8; font-size: 14px', 'color: #94a3b8; font-size: 14px')
    body = body.replace('border-top: 1px solid #93c5fd', 'border-top: 1px solid #e2e8f0')
    body = body.replace('font-weight: 600', 'font-weight: 400')
    body = body.replace('font-weight: 700', 'font-weight: 400')
    msg.write({
        'body': '<div style="pointer-events: none; user-select: none;">%s</div>'
                '<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 6px 14px; margin-top: 6px; text-align: center;">'
                '<span style="color: #16a34a; font-size: 12px; font-weight: 600;">Traité</span></div>' % body
    })
    _post_pending_summary(rec.env)


def _post_pending_summary(env):
    """Si des notifications sont encore en attente, reposte un résumé pour garder le canal foncé."""
    pending = 0
    pending += env['commercial.versement'].sudo().search_count([
        ('notified', '=', True), ('state', '=', 'brouillon')])
    pending += env['commercial.echeance'].sudo().search_count([
        ('notified', '=', True), ('etat', '=', 'brouillon')])
    pending += env['commercial.echeance.apport'].sudo().search_count([
        ('notified', '=', True), ('etat', '=', 'brouillon')])
    pending += env['commercial.echeance.apport.declare'].sudo().search_count([
        ('notified', '=', True), ('etat', '=', 'brouillon')])
    pending += env['commercial.echeance.coprop'].sudo().search_count([
        ('notified', '=', True), ('etat', '=', 'brouillon')])
    pending += env['commercial.echeance.ts'].sudo().search_count([
        ('notified', '=', True), ('etat', '=', 'brouillon')])
    if pending <= 0:
        return
    Channel = env['discuss.channel']
    channel = Channel.sudo().search([('name', '=', 'Validation Versements & Paiements')], limit=1)
    if not channel:
        return
    admin_group = env.ref('commercial.group_commercial_admin', raise_if_not_found=False)
    if not admin_group:
        return
    admin_partners = admin_group.users.mapped('partner_id')
    author = env.ref('base.partner_root')
    channel.sudo().message_post(
        author_id=author.id,
        body='<div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 10px 14px; border-radius: 8px;">'
             '<p style="color: #92400e; font-size: 14px; font-weight: bold; margin: 0;">📋 Il reste %d notification(s) en attente de validation.</p>'
             '</div>' % pending,
        body_is_html=True,
        message_type='comment',
        subtype_xmlid='mail.mt_comment',
        partner_ids=admin_partners.ids,
    )


class CommercialPaiement(models.Model):
    _name = 'commercial.paiement'
    _description = 'Fiche Paiement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    def _set_lot_vendu(self):
        """Set lot to 'vendu' on first echeance confirmation and clean up other partners."""
        for rec in self:
            if rec.lot_id and rec.lot_id.state in ('disponible', 'en_option', 'reserve'):
                rec.lot_id.write({'state': 'vendu'})
                # Remove lot from other contacts and save to their history
                if rec.client_id:
                    other_partners = self.env['res.partner'].search([
                        ('commercial_lot_ids', 'in', rec.lot_id.id),
                        ('id', '!=', rec.client_id.id),
                    ])
                    for partner in other_partners:
                        partner.with_context(force_lot_release=True).write({
                            'commercial_lot_ids': [(3, rec.lot_id.id)],
                            'commercial_lot_history_ids': [(4, rec.lot_id.id)],
                        })

    def _check_lot_prereservation(self):
        """Remettre le lot en pré-réservation si aucune échéance payée et aucun versement confirmé."""
        for rec in self:
            if not rec.lot_id:
                continue
            has_echeance_payee = rec.echeance_ids.filtered(lambda e: e.etat == 'paye')
            has_echeance_apport_payee = rec.echeance_apport_ids.filtered(lambda e: e.etat == 'paye')
            has_versement_confirme = rec.lot_id.versement_ids.filtered(
                lambda v: v.state == 'confirme' and not v.client_id.is_blocked)
            if not has_echeance_payee and not has_echeance_apport_payee and not has_versement_confirme:
                rec.lot_id.write({'state': 'en_option'})

    active = fields.Boolean(string="Actif", default=True, tracking=True)
    name = fields.Char(string="Référence", compute='_compute_name', store=True)
    lot_id = fields.Many2one('commercial.lot', string="Lot", required=True, ondelete='cascade', tracking=True)
    client_id = fields.Many2one('res.partner', string="Client", ondelete='cascade', tracking=True)
    montant_lot = fields.Float(string="Montant du lot", compute='_compute_montant_lot', store=True, tracking=True)

    @api.depends('lot_id.montant_net_client')
    def _compute_montant_lot(self):
        for rec in self:
            rec.montant_lot = rec.lot_id.montant_net_client if rec.lot_id else 0.0

    type_paiement = fields.Selection([
        ('cache', 'Cache'),
        ('tranche', 'Tranche'),
        ('cb', 'Crédit Bancaire'),
    ], string="Mode de paiement", tracking=True)

    montant_a_payer = fields.Float(
        string="Montant à payer", compute='_compute_montant_a_payer', store=True)

    montant_deja_paye = fields.Float(
        string="Montant déjà payé", compute='_compute_montant_deja_paye', store=True)
    reste = fields.Float(
        string="Reste à payer", compute='_compute_reste', store=True)

    # Copropriété
    montant_coprop = fields.Float(string="Coprop.", tracking=True)
    echeance_coprop_ids = fields.One2many(
        'commercial.echeance.coprop', 'paiement_id', string="Échéances Coprop.")
    montant_paye_coprop = fields.Float(
        string="Montant payé Coprop.", compute='_compute_montant_paye_coprop', store=True)
    reste_coprop = fields.Float(
        string="Reste Coprop.", compute='_compute_reste_coprop', store=True)

    # Montant Global Client
    montant_global_client = fields.Float(
        string="Montant global client", compute='_compute_montant_global_client', store=True)

    # Travaux Supplémentaires
    nom_travaux_supp = fields.Char(string="Nom des travaux", tracking=True)
    montant_travaux_supp = fields.Float(string="Montant TS", tracking=True)
    echeance_ts_ids = fields.One2many(
        'commercial.echeance.ts', 'paiement_id', string="Échéances TS")
    montant_paye_ts = fields.Float(
        string="Montant payé TS", compute='_compute_montant_paye_ts', store=True)
    reste_ts = fields.Float(
        string="Reste TS", compute='_compute_reste_ts', store=True)

    echeance_ids = fields.One2many('commercial.echeance', 'paiement_id', string="Échéances")

    # Champs spécifiques Crédit Bancaire
    banque_id = fields.Many2one('res.partner.bank', string="Banque")
    montant_declare = fields.Float(string="Montant déclaré", tracking=True)
    montant_accorde = fields.Float(string="Montant accordé", tracking=True)
    apport_personnel = fields.Float(
        string="AP non déclaré", compute='_compute_apport_personnel', store=True)
    apport_declare = fields.Float(
        string="AP déclaré", compute='_compute_apport_declare', store=True)
    banque_apport_declare_id = fields.Many2one(
        'res.partner.bank', string="Banque AP déclaré")
    apport_global = fields.Float(
        string="AP global", compute='_compute_apport_global', store=True)
    is_locked = fields.Boolean(
        string="Verrouillé", compute='_compute_is_locked', store=True)
    montant_paye_cb = fields.Float(
        string="Montant payé CB", compute='_compute_montant_paye_cb', store=True)
    reste_cb = fields.Float(
        string="Reste par CB", compute='_compute_reste_cb', store=True)
    montant_paye_client = fields.Float(string="Montant payé par AP")
    montant_deja_paye_apport = fields.Float(
        string="Montant payé par AP", compute='_compute_montant_deja_paye_apport', store=True)
    reste_apport = fields.Float(
        string="Reste par AP", compute='_compute_reste_apport', store=True)
    montant_total_paye = fields.Float(
        string="Montant total payé", compute='_compute_montant_total_paye', store=True)
    reste_total = fields.Float(
        string="Reste total", compute='_compute_reste_total', store=True)
    echeance_apport_ids = fields.One2many(
        'commercial.echeance.apport', 'paiement_id', string="Échéances Apport Personnel")
    echeance_apport_declare_ids = fields.One2many(
        'commercial.echeance.apport.declare', 'paiement_id', string="Échéances AP Déclaré")
    montant_paye_apport_declare = fields.Float(
        string="Montant payé AP déclaré", compute='_compute_montant_paye_apport_declare', store=True)
    reste_apport_declare = fields.Float(
        string="Reste AP déclaré", compute='_compute_reste_apport_declare', store=True)

    @api.depends('client_id', 'lot_id')
    def _compute_name(self):
        for rec in self:
            parts = ["Fiche Paiement"]
            if rec.client_id:
                parts.append(rec.client_id.name)
            if rec.lot_id:
                parts.append(rec.lot_id.numero_lot or '')
            rec.name = " - ".join(parts)

    @api.onchange('lot_id')
    def _onchange_lot_id(self):
        if self.lot_id:
            # Don't override client_id — it comes from the contact form context
            pass

    @api.depends('montant_lot', 'lot_id.versement_ids.montant', 'lot_id.versement_ids.state',
                 'lot_id.versement_ids.montant_restant')
    def _compute_montant_a_payer(self):
        for rec in self:
            versements = 0.0
            if rec.lot_id:
                # Exclure les versements des clients bloqués
                for v in rec.lot_id.versement_ids:
                    if v.client_id.is_blocked:
                        continue
                    if v.state == 'confirme':
                        versements += v.montant
                    elif v.state == 'partiellement_rembourse':
                        versements += v.montant_restant
            rec.montant_a_payer = rec.montant_lot - versements

    @api.onchange('type_paiement')
    def _onchange_type_paiement(self):
        # Supprimer les échéances brouillon de toutes les listes
        self.echeance_ids = self.echeance_ids.filtered(lambda e: e.etat != 'brouillon')
        self.echeance_apport_ids = self.echeance_apport_ids.filtered(lambda e: e.etat != 'brouillon')
        self.echeance_apport_declare_ids = self.echeance_apport_declare_ids.filtered(lambda e: e.etat != 'brouillon')

        # Créer les nouvelles échéances selon le type choisi
        if self.type_paiement == 'cache':
            self.update({'echeance_ids': [(0, 0, {
                'numero': 1,
                'pourcentage': 100,
                'montant': self.montant_a_payer,
            })]})
        elif self.type_paiement == 'tranche':
            pass
        elif self.type_paiement == 'cb':
            tranches = [20, 15, 35, 25, 5]
            self.update({'echeance_ids': [(0, 0, {
                'numero': i + 1,
                'pourcentage': p,
            }) for i, p in enumerate(tranches)]})

    @api.onchange('echeance_ids')
    def _onchange_echeance_ids(self):
        for i, line in enumerate(self.echeance_ids, start=1):
            line.numero = i

    @api.onchange('echeance_apport_ids')
    def _onchange_echeance_apport_ids(self):
        for i, line in enumerate(self.echeance_apport_ids, start=1):
            line.numero = i

    @api.onchange('echeance_apport_declare_ids')
    def _onchange_echeance_apport_declare_ids(self):
        for i, line in enumerate(self.echeance_apport_declare_ids, start=1):
            line.numero = i

    @api.onchange('echeance_coprop_ids')
    def _onchange_echeance_coprop_ids(self):
        for i, line in enumerate(self.echeance_coprop_ids, start=1):
            line.numero = i

    @api.onchange('echeance_ts_ids')
    def _onchange_echeance_ts_ids(self):
        for i, line in enumerate(self.echeance_ts_ids, start=1):
            line.numero = i

    def write(self, vals):
        if 'type_paiement' in vals:
            for rec in self:
                if rec.type_paiement != vals['type_paiement']:
                    rec.echeance_ids.filtered(lambda e: e.etat == 'brouillon').unlink()
                    rec.echeance_apport_ids.filtered(lambda e: e.etat == 'brouillon').unlink()
                    rec.echeance_apport_declare_ids.filtered(lambda e: e.etat == 'brouillon').unlink()
            # Nettoyer les commandes pour éviter les conflits avec les enregistrements déjà supprimés
            for field in ('echeance_ids', 'echeance_apport_ids', 'echeance_apport_declare_ids'):
                if field in vals and isinstance(vals[field], list):
                    vals[field] = [cmd for cmd in vals[field]
                                   if not (isinstance(cmd, (list, tuple)) and cmd[0] == 2)]
        return super().write(vals)

    def unlink(self):
        for rec in self:
            has_confirmed = (
                    rec.echeance_ids.filtered(lambda e: e.etat == 'paye') or
                    rec.echeance_apport_ids.filtered(lambda e: e.etat == 'paye')
            )
            if has_confirmed:
                raise UserError(
                    "Impossible de supprimer la fiche paiement '%s' car elle contient des échéances confirmées."
                    % rec.name)
        return super().unlink()

    def action_archive(self):
        for rec in self:
            if rec.active:
                has_paye = (
                        rec.echeance_ids.filtered(lambda e: e.etat == 'paye') or
                        rec.echeance_apport_ids.filtered(lambda e: e.etat == 'paye')
                )
                if has_paye:
                    raise UserError(
                        "Impossible d'archiver la fiche '%s' car elle contient encore des échéances payées. "
                        "Veuillez d'abord les annuler." % rec.name)
        return super().action_archive()

    @api.depends('echeance_ids.etat', 'echeance_apport_ids.etat')
    def _compute_is_locked(self):
        for rec in self:
            rec.is_locked = (
                    any(e.etat == 'paye' for e in rec.echeance_ids) or
                    any(e.etat == 'paye' for e in rec.echeance_apport_ids)
            )

    @api.constrains('montant_declare', 'type_paiement')
    def _check_montant_declare_cb(self):
        for rec in self:
            if rec.type_paiement == 'cb' and not rec.montant_declare:
                raise ValidationError(
                    "Le montant déclaré est obligatoire pour le mode de paiement Crédit Bancaire.")

    @api.depends('montant_a_payer', 'montant_declare')
    def _compute_apport_personnel(self):
        for rec in self:
            rec.apport_personnel = rec.montant_a_payer - rec.montant_declare

    @api.depends('montant_declare', 'montant_accorde')
    def _compute_apport_declare(self):
        for rec in self:
            rec.apport_declare = rec.montant_declare - rec.montant_accorde

    @api.depends('apport_personnel', 'apport_declare')
    def _compute_apport_global(self):
        for rec in self:
            rec.apport_global = rec.apport_personnel + rec.apport_declare

    @api.depends('echeance_apport_ids.montant', 'echeance_apport_ids.etat')
    def _compute_montant_deja_paye_apport(self):
        for rec in self:
            rec.montant_deja_paye_apport = sum(
                e.montant for e in rec.echeance_apport_ids if e.etat == 'paye'
            )

    @api.depends('apport_personnel', 'montant_deja_paye_apport')
    def _compute_reste_apport(self):
        for rec in self:
            rec.reste_apport = rec.apport_personnel - rec.montant_deja_paye_apport

    @api.depends('echeance_apport_declare_ids.montant', 'echeance_apport_declare_ids.etat')
    def _compute_montant_paye_apport_declare(self):
        for rec in self:
            rec.montant_paye_apport_declare = sum(
                e.montant for e in rec.echeance_apport_declare_ids if e.etat == 'paye'
            )

    @api.depends('apport_declare', 'montant_paye_apport_declare')
    def _compute_reste_apport_declare(self):
        for rec in self:
            rec.reste_apport_declare = rec.apport_declare - rec.montant_paye_apport_declare

    @api.depends('echeance_ids.montant', 'echeance_ids.etat',
                 'echeance_apport_ids.montant', 'echeance_apport_ids.etat',
                 'lot_id.versement_ids.montant', 'lot_id.versement_ids.state',
                 'lot_id.versement_ids.montant_restant')
    def _compute_montant_deja_paye(self):
        for rec in self:
            montant = 0.0
            # Versements confirmés (exclure clients bloqués)
            if rec.lot_id:
                for v in rec.lot_id.versement_ids:
                    if v.client_id.is_blocked:
                        continue
                    if v.state == 'confirme':
                        montant += v.montant
                    elif v.state == 'partiellement_rembourse':
                        montant += v.montant_restant
            # Échéances paiement confirmées
            montant += sum(e.montant for e in rec.echeance_ids if e.etat == 'paye')
            # Échéances AP confirmées
            montant += sum(e.montant for e in rec.echeance_apport_ids if e.etat == 'paye')
            rec.montant_deja_paye = montant

    @api.depends('montant_lot', 'montant_deja_paye')
    def _compute_reste(self):
        for rec in self:
            rec.reste = rec.montant_lot - rec.montant_deja_paye

    @api.depends('echeance_ids.montant', 'echeance_ids.etat')
    def _compute_montant_paye_cb(self):
        for rec in self:
            rec.montant_paye_cb = sum(
                e.montant for e in rec.echeance_ids if e.etat == 'paye')

    @api.depends('montant_accorde', 'montant_paye_cb')
    def _compute_reste_cb(self):
        for rec in self:
            rec.reste_cb = rec.montant_accorde - rec.montant_paye_cb

    @api.depends('montant_deja_paye', 'montant_deja_paye_apport')
    def _compute_montant_total_paye(self):
        for rec in self:
            rec.montant_total_paye = rec.montant_deja_paye + rec.montant_deja_paye_apport

    @api.depends('reste_cb', 'reste_apport')
    def _compute_reste_total(self):
        for rec in self:
            rec.reste_total = rec.reste_cb + rec.reste_apport

    @api.depends('echeance_coprop_ids.montant', 'echeance_coprop_ids.etat')
    def _compute_montant_paye_coprop(self):
        for rec in self:
            rec.montant_paye_coprop = sum(
                e.montant for e in rec.echeance_coprop_ids if e.etat == 'paye')

    @api.depends('montant_coprop', 'montant_paye_coprop')
    def _compute_reste_coprop(self):
        for rec in self:
            rec.reste_coprop = rec.montant_coprop - rec.montant_paye_coprop

    @api.depends('montant_lot', 'montant_coprop', 'montant_travaux_supp')
    def _compute_montant_global_client(self):
        for rec in self:
            rec.montant_global_client = rec.montant_lot + rec.montant_coprop + rec.montant_travaux_supp

    @api.depends('echeance_ts_ids.montant', 'echeance_ts_ids.etat')
    def _compute_montant_paye_ts(self):
        for rec in self:
            rec.montant_paye_ts = sum(
                e.montant for e in rec.echeance_ts_ids if e.etat == 'paye')

    @api.depends('montant_travaux_supp', 'montant_paye_ts')
    def _compute_reste_ts(self):
        for rec in self:
            rec.reste_ts = rec.montant_travaux_supp - rec.montant_paye_ts

    def action_print_ordre_virement(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ordre de virement',
            'res_model': 'commercial.print.ordre.virement.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_paiement_id': self.id},
        }

    def action_print_coprop(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Imprimer Copropriété',
            'res_model': 'commercial.print.coprop.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_paiement_id': self.id},
        }



class CommercialEcheance(models.Model):
    _name = 'commercial.echeance'
    _description = 'Échéance de paiement'
    _order = 'numero'

    name = fields.Char(string="Référence", readonly=True, default='Nouveau', copy=False)
    paiement_id = fields.Many2one('commercial.paiement', string="Paiement", ondelete='cascade', required=True)
    numero = fields.Integer(string="N°")
    date = fields.Date(string="Date d'échéance")
    date_encaissement = fields.Date(string="Date d'encaissement")
    pourcentage = fields.Float(string="Pourcentage (%)")
    montant = fields.Float(string="Montant à payer", compute='_compute_montant', store=True, readonly=False)
    etat = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('paye', 'Payé'),
        ('annule', 'Annulé'),
    ], string="État", default='brouillon')
    notif_3j_envoyee = fields.Boolean(string="Notif J-3 envoyée", default=False)
    notif_jour_j_envoyee = fields.Boolean(string="Notif Jour J envoyée", default=False)
    caisse_entry_id = fields.Many2one('caisse.entry', string="Encaissement caisse", readonly=True, copy=False)
    notified = fields.Boolean(string="Notifié", default=False, copy=False)
    notification_message_id = fields.Many2one('mail.message', string="Message notification", copy=False)
    is_commercial_admin = fields.Boolean(compute='_compute_is_commercial_admin')

    def _compute_is_commercial_admin(self):
        is_admin = self.env.user.has_group('commercial.group_commercial_admin')
        for rec in self:
            rec.is_commercial_admin = is_admin

    def action_notifier(self):
        self.ensure_one()
        if self.paiement_id.type_paiement == 'cb':
            page = "Paiement CB"
        else:
            page = "Paiement"
        message = _notify_admin_echeance(self, "Nouvelle échéance à valider", page)
        if message:
            self.notification_message_id = message.id

    # Related fields for recap view
    client_id = fields.Many2one(related='paiement_id.client_id', string="Client", store=True, readonly=True)
    lot_id = fields.Many2one(related='paiement_id.lot_id', string="Lot", store=True, readonly=True)
    projet_id = fields.Many2one(related='paiement_id.lot_id.projet_id', string="Projet", store=True, readonly=True)

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "Échéance N°%s" % rec.numero
    type_paiement = fields.Selection(related='paiement_id.type_paiement', string="Type paiement", store=True,
                                     readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.numero:
                max_num = self.search([
                    ('paiement_id', '=', rec.paiement_id.id),
                    ('id', '!=', rec.id),
                ], order='numero desc', limit=1).numero
                rec.numero = max_num + 1
        return records

    def unlink(self):
        paiement_ids = self.mapped('paiement_id')
        for rec in self:
            if rec.etat == 'paye':
                raise UserError(
                    "Impossible de supprimer l'échéance N°%s car elle est déjà payée."
                    % rec.numero)
        res = super().unlink()
        for paiement in paiement_ids:
            for i, ech in enumerate(paiement.echeance_ids.sorted('numero'), start=1):
                if ech.numero != i:
                    ech.write({'numero': i})
        return res

    def _create_caisse_entry(self):
        """Crée un encaissement dans la caisse selon le type de paiement."""
        self.ensure_one()
        paiement = self.paiement_id
        if paiement.type_paiement == 'cb':
            cashbox = self.env.ref('caisse2.caisse_verte')
        else:
            cashbox = self.env.ref('caisse2.caisse_espece_commerciale')
        if paiement.type_paiement == 'cb':
            description = "Credit-bancaire - %s - %s - %s" % (
                paiement.name or '',
                paiement.client_id.name or '',
                paiement.lot_id.projet_id.name or '')
        elif paiement.type_paiement == 'cache':
            description = "Cache - %s - %s - %s" % (
                paiement.name or '',
                paiement.client_id.name or '',
                paiement.lot_id.projet_id.name or '')
        else:
            description = "Tranche - %s - %s - %s" % (
                self.numero,
                paiement.client_id.name or '',
                paiement.lot_id.projet_id.name or '')
        vals = {
            'name': self.env['ir.sequence'].next_by_code('caisse.entry') or '/',
            'amount': self.montant,
            'amount_paid': self.montant,
            'amount_verse': self.montant,
            'amount_residual': 0,
            'description': description,
            'company_id': self.env.company.id,
            'user_id': self.env.uid,
            'cashbox_id': cashbox.id,
            'state': 'approuve',
        }
        if paiement.type_paiement == 'cb' and paiement.banque_id:
            vals['banque_id'] = paiement.banque_id.id
        entry = self.env['caisse.entry'].sudo().create(vals)
        return entry

    def action_confirmer_echeance(self):
        for rec in self:
            if not rec.montant:
                raise UserError("Impossible de confirmer l'échéance N°%s : le montant est à 0." % rec.numero)
            entry = rec._create_caisse_entry()
            if entry:
                rec.caisse_entry_id = entry.id
        self.write({'etat': 'paye', 'date_encaissement': fields.Date.today()})
        for rec in self:
            rec.paiement_id._set_lot_vendu()
            _mark_notification_done(rec)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': 'Confirmation',
                'message': 'Paiement confirmé avec succès.',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_annuler_echeance(self):
        for rec in self:
            if rec.caisse_entry_id:
                rec.caisse_entry_id.cashbox_id.sudo().total_amount -= rec.montant
                rec.caisse_entry_id.sudo().write({'state': 'draft'})
        self.write({'etat': 'annule'})
        for rec in self:
            rec.paiement_id._check_lot_prereservation()
            _mark_notification_done(rec)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': 'Annulation',
                'message': 'Paiement annulé avec succès.',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    @api.depends('pourcentage', 'paiement_id.montant_a_payer', 'paiement_id.montant_accorde',
                 'paiement_id.type_paiement')
    def _compute_montant(self):
        for rec in self:
            base = rec.paiement_id.montant_accorde if rec.paiement_id.type_paiement == 'cb' else rec.paiement_id.montant_a_payer
            if rec.pourcentage and base:
                rec.montant = base * rec.pourcentage / 100
            elif not rec.montant:
                rec.montant = 0.0

    @api.model
    def check_upcoming_echeances(self):
        """Notifier exactement 2 fois : 3 jours avant et le jour même de l'échéance."""
        today = fields.Date.today()
        target_date = today + timedelta(days=3)

        # Échéances J-3 pas encore notifiées
        echeances_3j = self.search([
            ('etat', '=', 'brouillon'),
            ('date', '=', target_date),
            ('notif_3j_envoyee', '=', False),
        ])
        # Échéances Jour J pas encore notifiées
        echeances_jour_j = self.search([
            ('etat', '=', 'brouillon'),
            ('date', '=', today),
            ('notif_jour_j_envoyee', '=', False),
        ])

        echeances_a_notifier = []
        for ech in echeances_3j:
            echeances_a_notifier.append((ech, 'j3'))
        for ech in echeances_jour_j:
            echeances_a_notifier.append((ech, 'jour_j'))

        if not echeances_a_notifier:
            return

        Channel = self.env['discuss.channel']
        channel = Channel.sudo().search([('name', '=', 'Échéances Paiement')], limit=1)
        if not channel:
            channel = Channel.sudo().create({
                'name': 'Échéances Paiement',
                'channel_type': 'channel',
            })

        admin_group = self.env.ref('base.group_system')
        admin_partners = admin_group.users.mapped('partner_id')

        existing_partner_ids = channel.sudo().channel_partner_ids.ids
        for partner in admin_partners:
            if partner.id not in existing_partner_ids:
                channel.sudo().write({'channel_partner_ids': [(4, partner.id)]})

        author_partner = self.env.ref('mail_bot.partner_odoo_bot', raise_if_not_found=False) \
                         or self.env.ref('base.partner_root')

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''

        for ech, notif_type in echeances_a_notifier:
            paiement = ech.paiement_id
            delai = "aujourd'hui" if notif_type == 'jour_j' else "dans 3 jours"
            record_url = f"{base_url}/web#id={paiement.id}&model=commercial.paiement&view_type=form"
            html_message = f"""
                <p><b>Échéance de paiement {delai} :</b></p>
                <p>Client : <b>{paiement.client_id.name or ''}</b></p>
                <p>Lot : <b>{paiement.lot_id.numero_lot or ''}</b></p>
                <p>Montant : <b>{ech.montant:,.2f}</b> — Date : <b>{ech.date}</b></p>
                <p><a href="{record_url}" target="_blank" rel="noopener">Ouvrir la fiche paiement</a></p>
            """
            channel.sudo().message_post(
                author_id=author_partner.id,
                body=html_message,
                body_is_html=True,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=admin_partners.ids,
            )
            # Marquer comme envoyée pour ne plus la renvoyer
            if notif_type == 'j3':
                ech.sudo().write({'notif_3j_envoyee': True})
            else:
                ech.sudo().write({'notif_jour_j_envoyee': True})

        return True


class CommercialEcheanceApport(models.Model):
    _name = 'commercial.echeance.apport'
    _description = "Échéance Apport Personnel"
    _order = 'numero'

    name = fields.Char(string="Référence", readonly=True, default='Nouveau', copy=False)

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "Échéance N°%s" % rec.numero
    paiement_id = fields.Many2one('commercial.paiement', string="Paiement", ondelete='cascade', required=True)
    numero = fields.Integer(string="N°")
    date = fields.Date(string="Date d'échéance")
    date_encaissement = fields.Date(string="Date d'encaissement")
    pourcentage = fields.Float(string="Pourcentage (%)")
    montant = fields.Float(string="Montant à payer", compute='_compute_montant', store=True, readonly=False)
    etat = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('paye', 'Payé'),
        ('annule', 'Annulé'),
    ], string="État", default='brouillon')
    caisse_entry_id = fields.Many2one('caisse.entry', string="Encaissement caisse", readonly=True, copy=False)
    notified = fields.Boolean(string="Notifié", default=False, copy=False)
    notification_message_id = fields.Many2one('mail.message', string="Message notification", copy=False)
    is_commercial_admin = fields.Boolean(compute='_compute_is_commercial_admin')

    def _compute_is_commercial_admin(self):
        is_admin = self.env.user.has_group('commercial.group_commercial_admin')
        for rec in self:
            rec.is_commercial_admin = is_admin

    def action_notifier(self):
        self.ensure_one()
        message = _notify_admin_echeance(self, "Nouvelle échéance AP à valider", "Paiement AP non déclaré")
        if message:
            self.notification_message_id = message.id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.name or rec.name == 'Nouveau':
                rec.name = self.env['ir.sequence'].next_by_code('commercial.echeance.apport') or 'Nouveau'
            if not rec.numero:
                max_num = self.search([
                    ('paiement_id', '=', rec.paiement_id.id),
                    ('id', '!=', rec.id),
                ], order='numero desc', limit=1).numero
                rec.numero = max_num + 1
        return records

    def unlink(self):
        paiement_ids = self.mapped('paiement_id')
        for rec in self:
            if rec.etat == 'paye':
                raise UserError(
                    "Impossible de supprimer l'échéance apport N°%s car elle est déjà payée."
                    % rec.numero)
        res = super().unlink()
        for paiement in paiement_ids:
            for i, ech in enumerate(paiement.echeance_apport_ids.sorted('numero'), start=1):
                if ech.numero != i:
                    ech.write({'numero': i})
        return res

    def _create_caisse_entry(self):
        """Crée un encaissement (apport personnel)."""
        self.ensure_one()
        paiement = self.paiement_id
        cashbox = self.env.ref('caisse2.caisse_espece_commerciale')
        description = "Apport Personnel N°%s - Client: %s - Lot: %s - Projet: %s" % (
            self.numero, paiement.client_id.name or '',
            paiement.lot_id.numero_lot or '', paiement.lot_id.projet_id.name or '')
        entry = self.env['caisse.entry'].sudo().create({
            'name': self.env['ir.sequence'].next_by_code('caisse.entry') or '/',
            'amount': self.montant,
            'amount_paid': self.montant,
            'amount_verse': self.montant,
            'amount_residual': 0,
            'description': description,
            'company_id': self.env.company.id,
            'user_id': self.env.uid,
            'cashbox_id': cashbox.id,
            'state': 'approuve',
        })
        return entry

    def action_confirmer_echeance_apport(self):
        for rec in self:
            if not rec.montant:
                raise UserError("Impossible de confirmer l'échéance AP N°%s : le montant est à 0." % rec.numero)
            entry = rec._create_caisse_entry()
            if entry:
                rec.caisse_entry_id = entry.id
        self.write({'etat': 'paye', 'date_encaissement': fields.Date.today()})
        for rec in self:
            rec.paiement_id._set_lot_vendu()
            _mark_notification_done(rec)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': 'Confirmation',
                'message': 'Paiement AP confirmé avec succès.',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_annuler_echeance_apport(self):
        for rec in self:
            if rec.caisse_entry_id:
                rec.caisse_entry_id.cashbox_id.sudo().total_amount -= rec.montant
                rec.caisse_entry_id.sudo().write({'state': 'draft'})
        self.write({'etat': 'annule'})
        for rec in self:
            rec.paiement_id._check_lot_prereservation()
            _mark_notification_done(rec)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': 'Annulation',
                'message': 'Paiement AP annulé avec succès.',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    @api.depends('pourcentage', 'paiement_id.apport_personnel')
    def _compute_montant(self):
        for rec in self:
            if rec.pourcentage and rec.paiement_id.apport_personnel:
                rec.montant = rec.paiement_id.apport_personnel * rec.pourcentage / 100
            elif not rec.montant:
                rec.montant = 0.0


class CommercialEcheanceApportDeclare(models.Model):
    _name = 'commercial.echeance.apport.declare'
    _description = "Échéance Apport Personnel Déclaré"
    _order = 'numero'

    name = fields.Char(string="Référence", readonly=True, default='Nouveau', copy=False)

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "Échéance N°%s" % rec.numero
    paiement_id = fields.Many2one('commercial.paiement', string="Paiement", ondelete='cascade', required=True)
    numero = fields.Integer(string="N°")
    date = fields.Date(string="Date d'échéance")
    date_encaissement = fields.Date(string="Date d'encaissement")
    pourcentage = fields.Float(string="Pourcentage (%)")
    montant = fields.Float(string="Montant à payer", compute='_compute_montant', store=True, readonly=False)
    etat = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('paye', 'Payé'),
        ('annule', 'Annulé'),
    ], string="État", default='brouillon')
    caisse_entry_id = fields.Many2one('caisse.entry', string="Encaissement caisse", readonly=True, copy=False)
    notified = fields.Boolean(string="Notifié", default=False, copy=False)
    notification_message_id = fields.Many2one('mail.message', string="Message notification", copy=False)
    is_commercial_admin = fields.Boolean(compute='_compute_is_commercial_admin')

    def _compute_is_commercial_admin(self):
        is_admin = self.env.user.has_group('commercial.group_commercial_admin')
        for rec in self:
            rec.is_commercial_admin = is_admin

    def action_notifier(self):
        self.ensure_one()
        message = _notify_admin_echeance(self, "Nouvelle échéance AP déclaré à valider", "Paiement AP déclaré")
        if message:
            self.notification_message_id = message.id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.name or rec.name == 'Nouveau':
                rec.name = self.env['ir.sequence'].next_by_code('commercial.echeance.apport.declare') or 'Nouveau'
            if not rec.numero:
                max_num = self.search([
                    ('paiement_id', '=', rec.paiement_id.id),
                    ('id', '!=', rec.id),
                ], order='numero desc', limit=1).numero
                rec.numero = max_num + 1
        return records

    def unlink(self):
        paiement_ids = self.mapped('paiement_id')
        for rec in self:
            if rec.etat == 'paye':
                raise UserError(
                    "Impossible de supprimer l'échéance AP déclaré N°%s car elle est déjà payée."
                    % rec.numero)
        res = super().unlink()
        for paiement in paiement_ids:
            for i, ech in enumerate(paiement.echeance_apport_declare_ids.sorted('numero'), start=1):
                if ech.numero != i:
                    ech.write({'numero': i})
        return res

    def _create_caisse_entry(self):
        """Crée un encaissement (apport personnel déclaré)."""
        self.ensure_one()
        paiement = self.paiement_id
        cashbox = self.env.ref('caisse2.caisse_verte')
        description = "AP Déclaré N°%s - Client: %s - Lot: %s - Projet: %s" % (
            self.numero, paiement.client_id.name or '',
            paiement.lot_id.numero_lot or '', paiement.lot_id.projet_id.name or '')
        vals = {
            'name': self.env['ir.sequence'].next_by_code('caisse.entry') or '/',
            'amount': self.montant,
            'amount_paid': self.montant,
            'amount_verse': self.montant,
            'amount_residual': 0,
            'description': description,
            'company_id': self.env.company.id,
            'user_id': self.env.uid,
            'cashbox_id': cashbox.id,
            'state': 'approuve',
        }
        if paiement.banque_apport_declare_id:
            vals['banque_id'] = paiement.banque_apport_declare_id.id
        entry = self.env['caisse.entry'].sudo().create(vals)
        return entry

    def action_confirmer_echeance_apport_declare(self):
        for rec in self:
            if not rec.montant:
                raise UserError("Impossible de confirmer l'échéance AP déclaré N°%s : le montant est à 0." % rec.numero)
            entry = rec._create_caisse_entry()
            if entry:
                rec.caisse_entry_id = entry.id
        self.write({'etat': 'paye', 'date_encaissement': fields.Date.today()})
        for rec in self:
            rec.paiement_id._set_lot_vendu()
            _mark_notification_done(rec)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': 'Confirmation',
                'message': 'Paiement AP déclaré confirmé avec succès.',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_annuler_echeance_apport_declare(self):
        for rec in self:
            if rec.caisse_entry_id:
                rec.caisse_entry_id.cashbox_id.sudo().total_amount -= rec.montant
                rec.caisse_entry_id.sudo().write({'state': 'draft'})
        self.write({'etat': 'annule'})
        for rec in self:
            rec.paiement_id._check_lot_prereservation()
            _mark_notification_done(rec)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': 'Annulation',
                'message': 'Paiement AP déclaré annulé avec succès.',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    @api.depends('pourcentage', 'paiement_id.apport_declare')
    def _compute_montant(self):
        for rec in self:
            if rec.pourcentage and rec.paiement_id.apport_declare:
                rec.montant = rec.paiement_id.apport_declare * rec.pourcentage / 100
            elif not rec.montant:
                rec.montant = 0.0


class CommercialEcheanceCoprop(models.Model):
    _name = 'commercial.echeance.coprop'
    _description = "Échéance Copropriété"
    _order = 'numero'

    paiement_id = fields.Many2one('commercial.paiement', string="Paiement", ondelete='cascade', required=True)
    numero = fields.Integer(string="N°")
    date = fields.Date(string="Date")
    montant = fields.Float(string="Montant")
    etat = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('paye', 'Payé'),
        ('annule', 'Annulé'),
    ], string="État", default='brouillon')
    caisse_entry_id = fields.Many2one(
        'caisse.entry', string="Encaissement", readonly=True, copy=False)
    notified = fields.Boolean(string="Notifié", default=False, copy=False)
    notification_message_id = fields.Many2one('mail.message', string="Message notification", copy=False)
    is_commercial_admin = fields.Boolean(compute='_compute_is_commercial_admin')

    def _compute_is_commercial_admin(self):
        is_admin = self.env.user.has_group('commercial.group_commercial_admin')
        for rec in self:
            rec.is_commercial_admin = is_admin

    def action_notifier(self):
        self.ensure_one()
        message = _notify_admin_echeance(self, "Nouvelle échéance Coprop. à valider", "Paiement Coprop.")
        if message:
            self.notification_message_id = message.id

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "Échéance N°%s" % rec.numero

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.numero:
                max_num = self.search([
                    ('paiement_id', '=', rec.paiement_id.id),
                    ('id', '!=', rec.id),
                ], order='numero desc', limit=1).numero
                rec.numero = max_num + 1
        return records

    def unlink(self):
        paiement_ids = self.mapped('paiement_id')
        res = super().unlink()
        for paiement in paiement_ids:
            for i, ech in enumerate(paiement.echeance_coprop_ids.sorted('numero'), start=1):
                if ech.numero != i:
                    ech.write({'numero': i})
        return res

    def _create_caisse_entry(self):
        """Crée un encaissement (copropriété)."""
        self.ensure_one()
        paiement = self.paiement_id
        cashbox = self.env.ref('caisse2.caisse_espece_commerciale')
        description = "Coprop - %s - %s - %s - %s" % (
            self.numero,
            paiement.client_id.name or '',
            paiement.lot_id.projet_id.name or '',
            paiement.lot_id.numero_lot or '')
        entry = self.env['caisse.entry'].sudo().create({
            'name': self.env['ir.sequence'].next_by_code('caisse.entry') or '/',
            'amount': self.montant,
            'amount_paid': self.montant,
            'amount_verse': self.montant,
            'amount_residual': 0,
            'description': description,
            'company_id': self.env.company.id,
            'user_id': self.env.uid,
            'cashbox_id': cashbox.id,
            'state': 'approuve',
        })
        return entry

    def action_confirmer_coprop(self):
        for rec in self:
            if not rec.montant:
                raise UserError("Impossible de confirmer l'échéance Coprop N°%s : le montant est à 0." % rec.numero)
            entry = rec._create_caisse_entry()
            if entry:
                rec.caisse_entry_id = entry.id
        self.write({'etat': 'paye', 'date': fields.Date.today()})
        for rec in self:
            _mark_notification_done(rec)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': 'Confirmation',
                'message': 'Paiement Coprop. confirmé avec succès.',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_annuler_coprop(self):
        for rec in self:
            if rec.caisse_entry_id:
                rec.caisse_entry_id.cashbox_id.sudo().total_amount -= rec.montant
                rec.caisse_entry_id.sudo().write({'state': 'draft'})
        self.write({'etat': 'annule'})
        for rec in self:
            _mark_notification_done(rec)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': 'Annulation',
                'message': 'Paiement Coprop. annulé avec succès.',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }


class CommercialEcheanceTS(models.Model):
    _name = 'commercial.echeance.ts'
    _description = "Échéance Travaux Supplémentaires"
    _order = 'numero'

    paiement_id = fields.Many2one('commercial.paiement', string="Paiement", ondelete='cascade', required=True)
    numero = fields.Integer(string="N°")
    date = fields.Date(string="Date")
    montant = fields.Float(string="Montant")
    etat = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('paye', 'Payé'),
        ('annule', 'Annulé'),
    ], string="État", default='brouillon')
    caisse_entry_id = fields.Many2one(
        'caisse.entry', string="Encaissement", readonly=True, copy=False)
    notified = fields.Boolean(string="Notifié", default=False, copy=False)
    notification_message_id = fields.Many2one('mail.message', string="Message notification", copy=False)
    is_commercial_admin = fields.Boolean(compute='_compute_is_commercial_admin')

    def _compute_is_commercial_admin(self):
        is_admin = self.env.user.has_group('commercial.group_commercial_admin')
        for rec in self:
            rec.is_commercial_admin = is_admin

    def action_notifier(self):
        self.ensure_one()
        message = _notify_admin_echeance(self, "Nouvelle échéance TS à valider", "Paiements TS")
        if message:
            self.notification_message_id = message.id

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "Échéance TS N°%s" % rec.numero

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.numero:
                max_num = self.search([
                    ('paiement_id', '=', rec.paiement_id.id),
                    ('id', '!=', rec.id),
                ], order='numero desc', limit=1).numero
                rec.numero = max_num + 1
        return records

    def unlink(self):
        paiement_ids = self.mapped('paiement_id')
        res = super().unlink()
        for paiement in paiement_ids:
            for i, ech in enumerate(paiement.echeance_ts_ids.sorted('numero'), start=1):
                if ech.numero != i:
                    ech.write({'numero': i})
        return res

    def _create_caisse_entry(self):
        """Crée un encaissement (travaux supplémentaires)."""
        self.ensure_one()
        paiement = self.paiement_id
        cashbox = self.env.ref('caisse2.caisse_espece_commerciale')
        description = "TS - %s - %s - %s - %s" % (
            self.numero,
            paiement.client_id.name or '',
            paiement.lot_id.projet_id.name or '',
            paiement.lot_id.numero_lot or '')
        entry = self.env['caisse.entry'].sudo().create({
            'name': self.env['ir.sequence'].next_by_code('caisse.entry') or '/',
            'amount': self.montant,
            'amount_paid': self.montant,
            'amount_verse': self.montant,
            'amount_residual': 0,
            'description': description,
            'company_id': self.env.company.id,
            'user_id': self.env.uid,
            'cashbox_id': cashbox.id,
            'state': 'approuve',
        })
        return entry

    def action_confirmer_ts(self):
        for rec in self:
            if not rec.montant:
                raise UserError("Impossible de confirmer l'échéance TS N°%s : le montant est à 0." % rec.numero)
            entry = rec._create_caisse_entry()
            if entry:
                rec.caisse_entry_id = entry.id
        self.write({'etat': 'paye', 'date': fields.Date.today()})
        for rec in self:
            _mark_notification_done(rec)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': 'Confirmation',
                'message': 'Paiement TS confirmé avec succès.',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_annuler_ts(self):
        for rec in self:
            if rec.caisse_entry_id:
                rec.caisse_entry_id.cashbox_id.sudo().total_amount -= rec.montant
                rec.caisse_entry_id.sudo().write({'state': 'draft'})
        self.write({'etat': 'annule'})
        for rec in self:
            _mark_notification_done(rec)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': 'Annulation',
                'message': 'Paiement TS annulé avec succès.',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }
