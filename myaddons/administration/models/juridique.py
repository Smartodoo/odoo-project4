
# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime, timedelta


class Juridique(models.Model):
    _name = 'administration.juridique'
    _description = 'Suivi Juridique'
    _inherit = ['mail.thread', 'mail.activity.mixin']


    date = fields.Date(string="Date")  # Date du dossier
    numero_affaire = fields.Char(string="N° Affaire")  # Numéro d'affaire
    partie = fields.Char(string="Partie")  # Nom de la partie concernée
    designation = fields.Char(string="Désignation")  # Désignation de l'affaire
    juridiction = fields.Char(string="Juridiction")  # Tribunal / cour
    section_chambre = fields.Char(string="Section / Chambre")  # Chambre ou section du tribunal
    date_audience = fields.Date(string="Date de l’Audience")  # Date d'audience
    observation = fields.Text(string="Observation")  # Observations diverses
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user)

    historique_audience_ids = fields.One2many(
        'administration.juridique.audience.historique',
        'juridique_id',
        string="Historique des audiences",

    )

    # ---- LOGIQUE AUTOMATIQUE ----
    @api.model
    def create(self, vals):
        record = super().create(vals)
        return record

    def write(self, vals):
        for rec in self:
            ancienne_date = rec.date_audience
            res = super(Juridique, rec).write(vals)

            # Si la date d’audience a changé, ajouter automatiquement dans l’historique
            if 'date_audience' in vals and ancienne_date and ancienne_date != vals['date_audience']:
                self.env['administration.juridique.audience.historique'].create({
                    'juridique_id': rec.id,
                    'ancienne_date': ancienne_date,
                })
        return res

        # ---- Fonction automatique de vérification des audiences proches ----

    @api.model
    def check_upcoming_audiences(self):
        """Notifier les administrateurs 3 jours avant les audiences"""
        today = fields.Date.today()
        target_date = today + timedelta(days=3)

        # Cherche les audiences prévues dans 3 jours
        records = self.search([('date_audience', '<=', target_date), ('date_audience', '>=', today)])
        if not records:
            return

        # Canal où seront postées les notifications
        Channel = self.env['discuss.channel']
        channel = Channel.sudo().search([('name', '=', 'Audiences à venir')], limit=1)
        if not channel:
            channel = Channel.sudo().create({
                'name': 'Audiences à venir',

                'channel_type': 'channel',  # Odoo 17
            })

        #  Récupère tous les administrateurs du système
        admin_group = self.env.ref('base.group_system')
        admin_partners = admin_group.users.mapped('partner_id')

        # Ajoute tous les administrateurs au canal (s’ils ne sont pas déjà)
        existing_partner_ids = channel.sudo().channel_partner_ids.ids
        for partner in admin_partners:
            if partner.id not in existing_partner_ids:
                channel.sudo().write({'channel_partner_ids': [(4, partner.id)]})

        #  Prépare l’auteur du message (OdooBot ou Admin)
        author_partner = self.env.ref('mail_bot.partner_odoo_bot', raise_if_not_found=False) \
                         or self.env.ref('base.partner_root')

        #  Poste une notification pour chaque audience
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        for record in records:
            record_url = f"{base_url}/web#id={record.id}&model=administration.juridique&view_type=form"
            html_message = f"""
                <p><b> Audience à venir :</b></p>
                <p>Le dossier <b>{record.numero_affaire or ''}</b> a une audience prévue le <b>{record.date_audience}</b>.</p>
                <p>👉 <a href="{record_url}" target="_blank" rel="noopener">Ouvrir le dossier</a></p>
            """

            channel.sudo().message_post(
                author_id=author_partner.id,
                body=html_message,
                body_is_html=True,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=admin_partners.ids,
            )

        return True


class JuridiqueAudienceHistorique(models.Model):
    _name = 'administration.juridique.audience.historique'
    _description = 'Historique des dates d’audience'

    juridique_id = fields.Many2one('administration.juridique', string="Affaire", ondelete='cascade')
    ancienne_date = fields.Date(string="Ancienne date d’audience")
    note = fields.Text(string="Note")