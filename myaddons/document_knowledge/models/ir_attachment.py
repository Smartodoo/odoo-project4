# Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models , api


class IrAttachment(models.Model):
    _inherit = ['ir.attachment']

    # Add index to res_model because filtering on it is a common use case
    res_model = fields.Char(index=True)
    date_exp = fields.Date(string="Date d'expiration ")




    @api.model
    def create(self, vals):
        ctx = self._context

        # CAS 1 : upload depuis un formulaire (bon comportement)
        if not vals.get('res_model') and ctx.get('active_model'):
            vals['res_model'] = ctx['active_model']

        if not vals.get('res_id') and ctx.get('active_id'):
            vals['res_id'] = ctx['active_id']


        return super().create(vals)



    @api.model
    def cron_notify_expired_attachments(self):
        """Notifier lorsque la date_exp = aujourd'hui"""
        today = fields.Date.today()

        # Chercher les pièces jointes qui expirent aujourd'hui
        records = self.search([('date_exp', '=', today)])
        if not records:
            return

        # Canal où seront envoyées les notifications
        Channel = self.env['discuss.channel']
        channel = Channel.sudo().search([('name', '=', 'Fichiers expirés')], limit=1)

        if not channel:
            channel = Channel.sudo().create({
                'name': 'Fichiers expirés',
                'channel_type': 'channel',
            })

        # Ajouter tous les administrateurs
        admin_group = self.env.ref('base.group_system')
        admin_partners = admin_group.users.mapped('partner_id')

        existing_partner_ids = channel.sudo().channel_partner_ids.ids
        for partner in admin_partners:
            if partner.id not in existing_partner_ids:
                channel.sudo().write({'channel_partner_ids': [(4, partner.id)]})

        # Auteur du message
        author_partner = self.env.ref('mail_bot.partner_odoo_bot', raise_if_not_found=False) \
                         or self.env.ref('base.partner_root')

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''

        # Envoyer une notification pour chaque fichier expiré
        for rec in records:
            rec_url = f"{base_url}/web#id={rec.id}&model=ir.attachment&view_type=form"
            html_message = f"""
                    <p><b>📁 Fichier expiré</b></p>
                    <p>Le fichier <b>{rec.name}</b> a expiré aujourd'hui.</p>
                    <p>👉 <a href="{rec_url}" target="_blank" rel="noopener">Ouvrir le fichier</a></p>
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

