# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import models, fields, api
from dateutil.relativedelta import relativedelta

class CreditBancaire(models.Model):
    _name = 'administration.credit.bancaire'
    _description = 'Suivi des Crédits Bancaires'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    reference = fields.Char(string="Référence", required=True)
    date_demande = fields.Date(string="Date de Demande")
    situation_financiere = fields.Char(string="Situation Financière")
    montant_global = fields.Float(string="Montant Global (DA/TTC)")
    taux_accorde = fields.Float(string="Taux Accordé (%)")
    taux_interet_annuel = fields.Float(string="Taux d’Intérêt Annuel (%)")
    capital_emprunte = fields.Float(string="Capital Emprunté (TTC)")
    duree_pret = fields.Integer(string="Durée du Prêt (mois)" , default=9)
    journalier = fields.Float(string="Journalier (360 jrs) / DA TTC", compute="_compute_journalier", store=True)
    date_credit = fields.Date(string="Date du Crédit")
    montant_interet_annuel = fields.Float(string="Montant Intérêt Annuel (HT)", compute="_compute_montant_intr_annuel",
                                          store=True)
    montant_interet_9_mois = fields.Float(string="Montant Intérêt sur 9 Mois (HT)",
                                          compute="_compute_montant_intr_mois", store=True)
    montant_270jrs = fields.Float(string="Montant sur 270 Jours", compute="_compute_montant_270jrs", store=True)
    tva_19 = fields.Float(string="TVA (19%)" , compute="_compute_tva_19" , store=True)
    montant_interet_ttc = fields.Float(string="Montant de l’Intérêt (TTC)", compute= "_compute_montant_interet_ttc", store=True)
    date_remboursement = fields.Date(string="Date de Remboursement", compute="_compute_date_remboursement", store=True)
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user)

    @api.depends('capital_emprunte', 'duree_pret')
    def _compute_journalier(self):
        for record in self:
            if record.capital_emprunte and record.duree_pret and record.duree_pret != 0:
                record.journalier = (record.capital_emprunte / record.duree_pret) / 30
            else:
                record.journalier = 0

    @api.depends('capital_emprunte', 'taux_interet_annuel')
    def _compute_montant_intr_annuel(self):
        for record in self:
            if record.capital_emprunte and record.taux_interet_annuel:
                record.montant_interet_annuel = (record.capital_emprunte * record.taux_interet_annuel) / 100
            else:
                record.montant_interet_annuel = 0

    @api.depends('montant_interet_annuel')
    def _compute_montant_intr_mois(self):
        for record in self:
            if record.montant_interet_annuel:
                record.montant_interet_9_mois = (record.montant_interet_annuel / 12) * 9
            else:
                record.montant_interet_9_mois = 0

    @api.depends('montant_interet_9_mois')
    def _compute_montant_270jrs(self):
        for record in self:
            if record.montant_interet_9_mois:
                record.montant_270jrs = record.montant_interet_9_mois / 270
            else:
                record.montant_270jrs = 0

    @api.depends('montant_interet_9_mois')
    def _compute_tva_19(self):
        for record in self:
            if record.montant_interet_9_mois:
                record.tva_19 = record.montant_interet_9_mois * 0.19
            else:
                record.tva_19 = 0

    @api.depends('montant_interet_9_mois', 'tva_19')
    def _compute_montant_interet_ttc(self):
        for record in self :
            if record.montant_interet_9_mois and record.tva_19:
                record.montant_interet_ttc = record.montant_interet_9_mois + record.tva_19
            else:
                record.montant_interet_ttc = 0

    @api.depends('date_credit')
    def _compute_date_remboursement(self):
        for rec in self:
            if rec.date_credit:
                rec.date_remboursement = rec.date_credit + relativedelta(months=9)
            else:
                rec.date_remboursement = False

    @api.model
    def check_upcoming_remboursements(self):
        """Notifier les administrateurs 15 jours avant la date de remboursement"""
        today = fields.Date.today()
        target_date = today + timedelta(days=15)

        # Cherche les enregistrements avec date_remboursement dans 15 jours
        records = self.search([('date_remboursement', '<=', target_date),('date_remboursement', '>=', today)])
        if not records:
            return

        # Canal où seront postées les notifications
        Channel = self.env['discuss.channel']
        channel = Channel.sudo().search([('name', '=', 'Notification Date Remboursement')], limit=1)
        if not channel:
            channel = Channel.sudo().create({
                'name': 'Notification Date Remboursement',
                'channel_type': 'channel',  # Odoo 17
            })


        # Récupère tous les administrateurs du système
        admin_group = self.env.ref('base.group_system')
        admin_partners = admin_group.users.mapped('partner_id')

        # Ajoute tous les administrateurs au canal (s’ils ne sont pas déjà)
        existing_partner_ids = channel.sudo().channel_partner_ids.ids
        for partner in admin_partners:
            if partner.id not in existing_partner_ids:
                channel.sudo().write({'channel_partner_ids': [(4, partner.id)]})

        # Prépare l’auteur du message (OdooBot ou Admin)
        author_partner = self.env.ref('mail_bot.partner_odoo_bot', raise_if_not_found=False) \
                         or self.env.ref('base.partner_root')

        # Poste une notification pour chaque remboursement
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        for record in records:
            record_url = f"{base_url}/web#id={record.id}&model={self._name}&view_type=form"
            html_message = f"""
                    <p><b> Remboursement à venir :</b></p>
                    <p>Le dossier <b>{getattr(record, 'situation_financiere', '')}</b> a un remboursement prévu le <b>{record.date_remboursement}</b>.</p>
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