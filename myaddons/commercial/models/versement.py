from odoo import models, fields, api
from odoo.exceptions import UserError
from .paiement import _mark_notification_done


class CommercialVersement(models.Model):
    _name = 'commercial.versement'
    _description = 'Versement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string="Référence", readonly=True, default='Nouveau', copy=False)
    lot_id = fields.Many2one('commercial.lot', string="Lot", required=True, ondelete='cascade', tracking=True)
    client_id = fields.Many2one('res.partner', string="Client", ondelete='cascade', tracking=True)
    projet_id = fields.Many2one('commercial.projet', string="Projet", tracking=True)
    bloc_id = fields.Many2one('commercial.bloc', string="Bloc", tracking=True)
    montant = fields.Float(string="Montant à verser", tracking=True)
    date = fields.Date(string="Date", default=fields.Date.context_today, required=True, tracking=True)
    date_encaissement = fields.Date(string="Date d'encaissement", readonly=True, tracking=True)
    mode_paiement = fields.Selection([
        ('especes', 'Espèces'),
        ('cheque', 'Chèque'),
        ('virement', 'Virement'),
    ], string="Mode de paiement", default='especes', tracking=True)
    active = fields.Boolean(string="Actif", default=True, tracking=True)
    note = fields.Text(string="Note")
    notified = fields.Boolean(string="Notifié", default=False, copy=False)
    notification_message_id = fields.Many2one('mail.message', string="Message notification", copy=False)
    is_commercial_admin = fields.Boolean(compute='_compute_is_commercial_admin')
    state = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('confirme', 'Confirmé'),
        ('partiellement_rembourse', 'Partiellement remboursé'),
        ('totalement_rembourse', 'Totalement remboursé'),
    ], string="État", default='brouillon', tracking=True)
    caisse_entry_id = fields.Many2one('caisse.entry', string="Encaissement caisse", readonly=True,
                                      tracking=True, copy=False)

    remboursement_ids = fields.One2many('commercial.remboursement', 'versement_id', string="Remboursements")
    montant_total_rembourse = fields.Float(
        string="Total remboursé", compute='_compute_montant_rembourse', store=True)
    montant_restant = fields.Float(
        string="Montant restant", compute='_compute_montant_rembourse', store=True)

    def _compute_is_commercial_admin(self):
        is_admin = self.env.user.has_group('commercial.group_commercial_admin')
        for rec in self:
            rec.is_commercial_admin = is_admin

    @api.depends('remboursement_ids.state', 'remboursement_ids.montant_rembourse', 'montant')
    def _compute_montant_rembourse(self):
        for rec in self:
            total = sum(r.montant_rembourse for r in rec.remboursement_ids if r.state == 'confirme')
            rec.montant_total_rembourse = total
            rec.montant_restant = rec.montant - total

    @api.constrains('montant', 'lot_id', 'client_id')
    def _check_montant_versement(self):
        for rec in self:
            if rec.lot_id and rec.client_id and rec.montant > 0:
                paiement = self.env['commercial.paiement'].search([
                    ('lot_id', '=', rec.lot_id.id),
                    ('client_id', '=', rec.client_id.id),
                ], limit=1)
                if paiement and rec.montant > paiement.reste:
                    raise UserError(
                        "Le montant du versement (%.2f) ne peut pas dépasser le reste à payer (%.2f)."
                        % (rec.montant, paiement.reste))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code('commercial.versement') or 'Nouveau'
            if vals.get('lot_id'):
                lot = self.env['commercial.lot'].browse(vals['lot_id'])
                if not vals.get('projet_id'):
                    vals['projet_id'] = lot.projet_id.id
                if not vals.get('bloc_id'):
                    vals['bloc_id'] = lot.bloc_id.id if lot.bloc_id else False
                # client_id is set via default_client_id from context, don't override it
        return super().create(vals_list)

    @api.onchange('lot_id')
    def _onchange_lot_id(self):
        if self.lot_id:
            self.projet_id = self.lot_id.projet_id
            self.bloc_id = self.lot_id.bloc_id
            # Don't override client_id — it comes from the contact form context

    def _get_cashbox(self):
        """Retourne la caisse selon le mode de paiement."""
        self.ensure_one()
        if self.mode_paiement in ('cheque', 'virement'):
            return self.env.ref('caisse2.caisse_verte')
        return self.env.ref('caisse2.caisse_espece_commerciale')

    def _create_caisse_entry(self):
        """Crée un encaissement dans la caisse appropriée."""
        self.ensure_one()
        cashbox = self._get_cashbox()
        description = "Versement %s - Client: %s - Lot: %s - Projet: %s" % (
            self.name, self.client_id.name or '',
            self.lot_id.numero_lot or '', self.projet_id.name or '')
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

    def action_notifier(self):
        self.ensure_one()
        admin_group = self.env.ref('commercial.group_commercial_admin', raise_if_not_found=False)
        if not admin_group:
            return
        Channel = self.env['discuss.channel']
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
        author = self.env.ref('base.partner_root')
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        url = f"{base_url}/web#id={self.id}&model=commercial.versement&view_type=form"
        html = f"""
            <div style="background: #dbeafe; border: 1px solid #93c5fd; border-left: 5px solid #2563eb; border-radius: 10px; padding: 18px 22px; margin: 8px 0; box-shadow: 0 2px 8px rgba(37,99,235,0.10);">
                <div style="display: flex; align-items: center; margin-bottom: 14px;">
                    <span style="background: #1d4ed8; color: #ffffff; font-size: 13px; font-weight: 700; padding: 4px 12px; border-radius: 20px; letter-spacing: 0.3px;">Nouveau versement</span>
                </div>
                <table style="width: 100%; font-size: 13px; color: #1e3a5f; border-collapse: collapse;">
                    <tr><td style="padding: 6px 0; width: 120px; color: #3b82f6; font-weight: 500;">Référence</td><td style="padding: 6px 0; font-weight: 600; color: #1e3a5f;">{self.name}</td></tr>
                    <tr><td style="padding: 6px 0; color: #3b82f6; font-weight: 500;">Client</td><td style="padding: 6px 0; font-weight: 600; color: #1e3a5f;">{self.client_id.name or ''}</td></tr>
                    <tr><td style="padding: 6px 0; color: #3b82f6; font-weight: 500;">Lot</td><td style="padding: 6px 0; font-weight: 600; color: #1e3a5f;">{self.lot_id.numero_lot or ''} <span style="color: #60a5fa;">—</span> Projet : {self.projet_id.name or ''}</td></tr>
                    <tr><td style="padding: 6px 0; color: #3b82f6; font-weight: 500;">Montant</td><td style="padding: 6px 0; font-weight: 700; color: #1d4ed8; font-size: 14px;">{self.montant:,.2f}</td></tr>
                    <tr><td style="padding: 6px 0; color: #3b82f6; font-weight: 500;">Créé par</td><td style="padding: 6px 0; font-weight: 600; color: #1e3a5f;">{self.env.user.name}</td></tr>
                </table>
                <div style="margin-top: 14px; padding-top: 12px; border-top: 1px solid #93c5fd;">
                    <a href="{url}" style="display: inline-block; background: #1d4ed8; color: #ffffff; padding: 8px 20px; border-radius: 6px; font-size: 13px; font-weight: 600; text-decoration: none;">Ouvrir le versement &rarr;</a>
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
        self.notified = True
        if message:
            self.notification_message_id = message.id

    def action_confirmer(self):
        for rec in self:
            if not rec.client_id:
                raise UserError("Le versement doit avoir un client assigné avant d'être confirmé.")
            if rec.montant <= 0:
                raise UserError("Impossible de confirmer un versement avec un montant égal à 0.")
            rec.state = 'confirme'
            rec.date_encaissement = fields.Date.today()
            # Créer l'encaissement dans la caisse
            entry = rec._create_caisse_entry()
            if entry:
                rec.caisse_entry_id = entry.id
            client = rec.client_id
            # If lot is still available or pre-reserved, move to reserved
            if rec.lot_id and rec.lot_id.state in ('disponible', 'en_option'):
                rec.lot_id.write({'state': 'reserve'})
            # Remove lot from other visitors and save to their history
            if rec.lot_id:
                other_partners = self.env['res.partner'].search([
                    ('commercial_lot_ids', 'in', rec.lot_id.id),
                    ('id', '!=', client.id),
                ])
                for partner in other_partners:
                    partner.with_context(force_lot_release=True).write({
                        'commercial_lot_ids': [(3, rec.lot_id.id)],
                        'commercial_lot_history_ids': [(4, rec.lot_id.id)],
                    })
            _mark_notification_done(rec)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': 'Confirmation',
                'message': 'Versement confirmé avec succès.',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_rembourser(self):
        self.ensure_one()
        if self.montant_restant <= 0:
            raise UserError("Ce versement est déjà totalement remboursé.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Remboursement',
            'res_model': 'commercial.remboursement',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_versement_id': self.id,
            },
        }

    def action_print_versement(self):
        self.ensure_one()
        return self.env.ref(
            'commercial.action_report_decharge_versement'
        ).report_action(self)

    def action_print_remboursement(self):
        self.ensure_one()
        wizard = self.env['commercial.print.remboursement.wizard'].create({
            'versement_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Imprimer remboursement',
            'res_model': 'commercial.print.remboursement.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }

    def action_archive(self):
        non_rembourse = self.filtered(lambda r: r.state != 'totalement_rembourse')
        if non_rembourse:
            raise UserError("Seuls les versements totalement remboursés peuvent être archivés.")
        return super().action_archive()

    def unlink(self):
        if not self.env.context.get('force_delete'):
            for rec in self:
                if rec.state != 'brouillon':
                    raise UserError("Seuls les versements en état brouillon peuvent être supprimés.")
        return super().unlink()
