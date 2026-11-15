from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import email_split, format_amount, format_date


class HotelReservationMailWizard(models.TransientModel):
    """« Envoyer mail » : informations du (des) client(s) d'une réservation.
    Depuis la fiche : une réservation. Depuis la liste : toutes les
    réservations cochées à l'état « Enregistrée », dans un seul mail."""
    _name = 'hotel.reservation.mail.wizard'
    _description = "Envoi d'un mail depuis une réservation"

    reservation_id = fields.Many2one(
        'hotel.reservation', string="Réservation", readonly=True)
    reservation_ids = fields.Many2many(
        'hotel.reservation', string="Réservations", readonly=True)
    skipped_info = fields.Char(string="Réservations ignorées", readonly=True)
    email_to = fields.Char(
        string="Destinataire", required=True,
        help="Adresse email du destinataire (plusieurs adresses séparées par une virgule).")
    subject = fields.Char(string="Objet", required=True)
    body = fields.Html(string="Message", sanitize_style=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        Reservation = self.env['hotel.reservation']
        if res.get('reservation_id'):
            # Fiche réservation : cette réservation
            reservations = Reservation.browse(res['reservation_id'])
            skipped = Reservation
        else:
            # Liste : réservations cochées -> « Enregistrée » seulement
            selection = Reservation.browse(
                ctx.get('active_ids') or ([ctx['active_id']] if ctx.get('active_id') else []))
            reservations = selection.filtered(lambda r: r.state == 'checkin')
            skipped = selection - reservations
            if selection and not reservations:
                raise UserError(_(
                    "Aucune des réservations sélectionnées n'est à l'état « Enregistrée »."))
        if not reservations:
            return res
        partners_email = list(filter(None, set(reservations.partner_id.mapped('email'))))
        res.update({
            'reservation_id': reservations.id if len(reservations) == 1 else False,
            'reservation_ids': [(6, 0, reservations.ids)],
            'email_to': partners_email[0] if len(partners_email) == 1 else False,
            'subject': (_("Réservation %s", reservations.name) if len(reservations) == 1
                        else _("Réservations enregistrées (%s)", len(reservations))),
            'body': (self._default_body(reservations) if len(reservations) == 1
                     else self._default_body_multi(reservations)),
            'skipped_info': skipped and _(
                "Ignorées (pas à l'état « Enregistrée ») : %s",
                ', '.join(skipped.mapped('name'))) or False,
        })
        return res

    def _client_rows(self, reservation):
        partner = reservation.partner_id
        id_types = dict(partner._fields['hotel_id_type'].selection)
        return [
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
            (_("Chambre(s)"), self._rooms_label(reservation)),
            (_("Total séjour"),
             format_amount(self.env, reservation.amount_total, reservation.currency_id)),
        ]

    def _rooms_label(self, reservation):
        rooms = ', '.join(dict.fromkeys(reservation.line_ids.mapped('room_id.name')))
        if reservation.booking_type == 'bed' and reservation.line_ids.bed_ids:
            return '%s (%s)' % (rooms, ', '.join(reservation.line_ids.bed_ids.mapped('name')))
        return rooms

    def _default_body(self, reservation):
        """Message pré-rempli avec les informations saisies sur le client."""
        lines = Markup('').join(
            Markup('<tr><td style="padding:4px 12px 4px 0;color:#7a7f96;">%s</td>'
                   '<td style="padding:4px 0;"><strong>%s</strong></td></tr>')
            % (label, value or '—')
            for label, value in self._client_rows(reservation))
        return Markup(
            '<p>Bonjour,</p>'
            '<p>Voici les informations de la réservation <strong>%s</strong> :</p>'
            '<table>%s</table>'
            '<p>Cordialement,<br/>%s</p>'
        ) % (reservation.name, lines, reservation.company_id.name or '')

    def _default_body_multi(self, reservations):
        """Plusieurs réservations : un tableau, une ligne par réservation."""
        labels = [label for label, value in self._client_rows(reservations[0])]
        cell = 'padding:4px 8px;border:1px solid #d8dbe5;'
        head = Markup('').join(
            Markup('<th style="%s background:#f1f3f8;text-align:left;">%s</th>') % (cell, label)
            for label in [_("Réservation")] + labels)
        body = Markup('').join(
            Markup('<tr>%s</tr>') % Markup('').join(
                Markup('<td style="%s">%s</td>') % (cell, value or '—')
                for value in [resa.name] + [v for _l, v in self._client_rows(resa)])
            for resa in reservations)
        return Markup(
            '<p>Bonjour,</p>'
            '<p>Voici les informations des %s réservations enregistrées :</p>'
            '<table style="border-collapse:collapse;">'
            '<thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
            '<p>Cordialement,<br/>%s</p>'
        ) % (len(reservations), head, body, reservations[0].company_id.name or '')

    def action_send(self):
        self.ensure_one()
        emails = email_split(self.email_to)
        if not emails:
            raise UserError(_("Saisissez une adresse email valide pour le destinataire."))
        reservations = self.reservation_ids or self.reservation_id
        if not reservations:
            raise UserError(_("Aucune réservation à envoyer."))
        first = reservations[0]
        mail = self.env['mail.mail'].sudo().create({
            'subject': self.subject,
            'body_html': self.body,
            'email_from': first.company_id.email_formatted or self.env.user.email_formatted,
            'email_to': ', '.join(emails),
            'model': first._name,
            'res_id': first.id if len(reservations) == 1 else False,
            'auto_delete': False,
        })
        mail.send()
        for reservation in reservations:
            reservation.message_post(
                body=Markup('%s<br/>%s') % (
                    _("Mail « %s » envoyé à %s", self.subject, ', '.join(emails)),
                    self.body or ''),
                subtype_xmlid='mail.mt_note')
        return {'type': 'ir.actions.act_window_close'}
