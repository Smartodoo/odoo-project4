from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError


class CommercialVersementLocation(models.Model):
    _name = 'commercial.versement.location'
    _inherit = ['mail.thread']
    _description = 'Versement Location'
    _rec_name = 'name'
    _order = 'date asc, id asc'

    name = fields.Char(
        string="Référence", readonly=True, copy=False, default='Nouveau')

    location_id = fields.Many2one(
        'commercial.location', string="Contrat", ondelete='cascade', required=True)
    lot_id = fields.Many2one(
        related='location_id.lot_id', string="Lot", store=True, readonly=True)
    client_location_id = fields.Many2one(
        related='location_id.client_location_id', string="Client", store=True, readonly=True)

    montant = fields.Float(string="Montant", required=True)
    date = fields.Date(string="Date", default=fields.Date.context_today)
    mode_paiement = fields.Selection([
        ('especes', 'Espèces'),
        ('cheque', 'Chèque'),
        ('virement', 'Virement'),
    ], string="Mode de paiement", default='especes')

    state = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('confirme', 'Confirmé'),
    ], string="Statut", default='brouillon', tracking=True)

    caisse_entry_id = fields.Many2one(
        'caisse.entry', string="Encaissement", readonly=True, copy=False)
    notif_3j_envoyee = fields.Boolean(default=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'commercial.versement.location') or 'Nouveau'
        return super().create(vals_list)

    def _create_caisse_entry(self):
        """Crée un encaissement dans la caisse appropriée."""
        self.ensure_one()
        cashbox = self.env.ref('caisse2.caisse_espece_commerciale')
        description = "Versement - %s - %s - %s" % (
            self.name or '',
            self.client_location_id.nom or '',
            self.location_id.projet_id.name or '')
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

    def action_confirmer(self):
        for rec in self:
            if rec.montant <= 0:
                raise UserError("Impossible de confirmer un versement avec un montant égal à 0.")
            rec.state = 'confirme'
            entry = rec._create_caisse_entry()
            if entry:
                rec.caisse_entry_id = entry.id
            rec._update_lot_state()

    def unlink(self):
        locations = self.mapped('location_id')
        result = super().unlink()
        for location in locations:
            if location.lot_id:
                self._update_lot_state_for_lot(location.lot_id)
        return result

    def _update_lot_state(self):
        """Met à jour l'état du lot depuis un versement."""
        for rec in self:
            if rec.location_id.lot_id:
                self._update_lot_state_for_lot(rec.location_id.lot_id, rec.location_id.client_location_id)

    def _update_lot_state_for_lot(self, lot, client_owner=None):
        """Met à jour l'état du lot selon les contrats location : loué seulement si un contrat est en_cours."""
        contrats = self.env['commercial.location'].search([('lot_id', '=', lot.id)])
        contrat_en_cours = False
        for contrat in contrats:
            if contrat.state == 'en_cours':
                contrat_en_cours = contrat
                break
        if contrat_en_cours:
            lot.state = 'loue'
            # Retirer le lot des autres clients location
            owner = client_owner or contrat_en_cours.client_location_id
            if owner:
                other_clients = self.env['commercial.client.location'].search([
                    ('lot_ids', 'in', lot.id),
                    ('id', '!=', owner.id),
                ])
                if other_clients:
                    other_clients.write({'lot_ids': [(3, lot.id)]})
        else:
            lot.state = 'disponible'

    @api.model
    def check_upcoming_versements_location(self):
        """Notifier 3 jours avant la date d'un versement de contrat de location."""
        today = fields.Date.today()
        target_date = today + timedelta(days=3)

        # Versements non confirmés dont la date est dans <= 3 jours (ou déjà dépassée)
        versements = self.search([
            ('state', '=', 'brouillon'),
            ('date', '<=', target_date),
            ('notif_3j_envoyee', '=', False),
            ('location_id.state', '=', 'en_cours'),
        ])

        if not versements:
            return

        # Créer / récupérer le canal Discuss
        Channel = self.env['discuss.channel']
        channel = Channel.sudo().search(
            [('name', '=', 'Rappel de Règlement - Contrat de Location')], limit=1)
        if not channel:
            channel = Channel.sudo().create({
                'name': 'Rappel de Règlement - Contrat de Location',
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

        for versement in versements:
            contrat = versement.location_id
            record_url = f"{base_url}/web#id={contrat.id}&model=commercial.location&view_type=form"
            html_message = f"""
                <p><b>Rappel de règlement - Contrat de location :</b></p>
                <p>Contrat : <b>{contrat.name or ''}</b></p>
                <p>Lot : <b>{contrat.lot_id.numero_lot or ''}</b> — Projet : <b>{contrat.projet_id.name or ''}</b></p>
                <p>Client : <b>{contrat.client_location_id.display_name or ''}</b></p>
                <p>Montant : <b>{versement.montant:,.2f}</b> — Date : <b>{versement.date}</b></p>
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
            versement.sudo().write({'notif_3j_envoyee': True})

        return True
