from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import email_split, format_amount, format_date


class HotelReservationMailWizard(models.TransientModel):
    _name = 'hotel.reservation.mail.wizard'
    _description = "Envoi d'un mail depuis une réservation"

    reservation_id = fields.Many2one(
        'hotel.reservation', string="Réservation", required=True, readonly=True)
    email_to = fields.Char(
        string="Destinataire", required=True,
        help="Adresse email du destinataire (plusieurs adresses séparées par une virgule).")
    subject = fields.Char(string="Objet", required=True)
    body = fields.Html(string="Message", sanitize_style=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        reservation = self.env['hotel.reservation'].browse(
            res.get('reservation_id') or self.env.context.get('active_id'))
        if reservation:
            res.update({
                'reservation_id': reservation.id,
                'email_to': reservation.partner_id.email or False,
                'subject': _("Réservation %s", reservation.name),
                'body': self._default_body(reservation),
            })
        return res

    def _default_body(self, reservation):
        """Message pré-rempli avec les informations saisies sur le client."""
        partner = reservation.partner_id
        id_types = dict(partner._fields['hotel_id_type'].selection)
        rows = [
            (_("Nom"), partner.hotel_last_name),
            (_("Prénom"), partner.hotel_first_name),
            (_("Date de naissance"),
             format_date(self.env, partner.hotel_birthdate) if partner.hotel_birthdate else ''),
            (_("Téléphone"), partner.phone),
            (_("Adresse"), partner.street),
            (_("Ville"), partner.city),
            (_("Pièce d'identité"), ' — '.join(filter(None, [
                id_types.get(partner.hotel_id_type, ''), partner.hotel_id_number]))),
            (_("Arrivée"), format_date(self.env, reservation.checkin) if reservation.checkin else ''),
            (_("Départ"), format_date(self.env, reservation.checkout) if reservation.checkout else ''),
            (_("Nuits"), reservation.nights),
            (_("Adultes / Enfants"), "%s / %s" % (reservation.adults, reservation.children)),
            (_("Chambre(s)"), ', '.join(reservation.line_ids.mapped('room_id.name'))),
            (_("Total séjour"),
             format_amount(self.env, reservation.amount_total, reservation.currency_id)),
        ]
        lines = Markup('').join(
            Markup('<tr><td style="padding:4px 12px 4px 0;color:#7a7f96;">%s</td>'
                   '<td style="padding:4px 0;"><strong>%s</strong></td></tr>')
            % (label, value or '—')
            for label, value in rows)
        return Markup(
            '<p>Bonjour,</p>'
            '<p>Voici les informations de la réservation <strong>%s</strong> :</p>'
            '<table>%s</table>'
            '<p>Cordialement,<br/>%s</p>'
        ) % (reservation.name, lines, reservation.company_id.name or '')

    def action_send(self):
        self.ensure_one()
        emails = email_split(self.email_to)
        if not emails:
            raise UserError(_("Saisissez une adresse email valide pour le destinataire."))
        reservation = self.reservation_id
        mail = self.env['mail.mail'].sudo().create({
            'subject': self.subject,
            'body_html': self.body,
            'email_from': reservation.company_id.email_formatted or self.env.user.email_formatted,
            'email_to': ', '.join(emails),
            'model': reservation._name,
            'res_id': reservation.id,
            'auto_delete': False,
        })
        mail.send()
        reservation.message_post(
            body=Markup('%s<br/>%s') % (
                _("Mail « %s » envoyé à %s", self.subject, ', '.join(emails)),
                self.body or ''),
            subtype_xmlid='mail.mt_note')
        return {'type': 'ir.actions.act_window_close'}
