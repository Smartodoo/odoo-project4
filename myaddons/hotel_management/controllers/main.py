# -*- coding: utf-8 -*-
import logging

from dateutil.relativedelta import relativedelta

from odoo import fields, http
from odoo.http import request
from odoo.tools import consteq

_logger = logging.getLogger(__name__)


class HotelWebsite(http.Controller):

    def _today_str(self):
        return fields.Date.to_string(fields.Date.context_today(request.env.user))

    def _parse_date(self, value):
        if not value:
            return None
        try:
            return fields.Date.from_string(value)
        except Exception:
            return None

    def _search_params(self, kw):
        checkin = kw.get('checkin') or ''
        checkout = kw.get('checkout') or ''
        try:
            guests = max(int(kw.get('guests') or 1), 1)
        except ValueError:
            guests = 1
        booking_type = self._booking_type(kw)
        # « accepter d'être séparés » : location au lit, plus d'une personne
        separate = bool(kw.get('separate')) and booking_type == 'bed' and guests > 1
        return checkin, checkout, guests, booking_type, separate

    def _site_types(self, booking_type):
        """Formules proposées : types actifs ayant un prix pour le mode."""
        fname = 'bed_price' if booking_type == 'bed' else 'room_price'
        return request.env['hotel.room.type'].sudo().search([(fname, '>', 0)])

    def _type_price(self, room_type, ci, co, guests, booking_type):
        """(prix / nuit, total du séjour) pour une formule : tarif saisonnier
        nuit par nuit, sinon prix du type ; au lit : x nombre de personnes."""
        room = request.env['hotel.room'].sudo().new({})
        unit = room._get_stay_unit_price(ci, co, booking_type, False, room_type)
        if booking_type == 'bed':
            unit *= guests
        nights = (co - ci).days if ci and co and co > ci else 0
        return unit, unit * nights

    @http.route(['/hotel', '/hotel/rooms'], type='http', auth='public',
                website=True, sitemap=True)
    def hotel_rooms(self, **kw):
        """Recherche : dates, personnes, chambre entière ou lit ; résultat =
        formules (types de chambre) disponibles avec leur prix total. Le
        client choisit ensuite sa chambre / ses lits parmi les propositions."""
        Room = request.env['hotel.room'].sudo()
        checkin, checkout, guests, booking_type, separate = self._search_params(kw)
        ci = self._parse_date(checkin)
        co = self._parse_date(checkout)
        error = None
        dates_selected = False
        cards = []
        if checkin or checkout:
            if not (ci and co and co > ci):
                error = "Veuillez saisir des dates valides (le départ doit suivre l'arrivée)."
            elif not booking_type:
                error = ("Choisissez le type de location (chambre entière ou lit "
                         "en dortoir) pour voir les disponibilités.")
            else:
                dates_selected = True
                bed_proposal = None
                for rtype in self._site_types(booking_type):
                    if booking_type == 'bed':
                        # par lit : la proposition ne dépend pas du type
                        if bed_proposal is None:
                            bed_proposal = Room._hotel_website_proposal(
                                ci, co, guests, 'bed', rtype, separate)
                        proposal = bed_proposal
                    else:
                        proposal = Room._hotel_website_proposal(ci, co, guests, 'room', rtype)
                    unit, total = self._type_price(rtype, ci, co, guests, booking_type)
                    cards.append({
                        'type': rtype,
                        'available': bool(proposal['rooms']),
                        'count': len(proposal['beds'] if booking_type == 'bed'
                                     else proposal['rooms']),
                        'unit': unit,
                        'total': total,
                    })
                cards.sort(key=lambda c: (not c['available'], c['total']))
        values = {
            'rooms': Room.search([('website_published', '=', True)]),
            'cards': cards,
            'dates_selected': dates_selected,
            'checkin': checkin,
            'checkout': checkout,
            'nights': (co - ci).days if dates_selected else 0,
            'guests': guests,
            'booking_type': booking_type,
            'separate': separate,
            'error': error,
            'today': self._today_str(),
            'currency': request.env.company.currency_id,
        }
        return request.render('hotel_management.rooms_page', values)

    def _booking_type(self, kw):
        """Type de location demandé : 'room' (chambre entière) ou 'bed' (lit en
        dortoir). Obligatoire pour une recherche avec dates ; '' = pas encore
        choisi (catalogue sans dates)."""
        value = kw.get('booking_type')
        return value if value in ('room', 'bed') else ''

    def _book_values(self, kw, **extra):
        """Valeurs de la page de réservation d'une formule : chambres / lits
        proposés par le système, prix, formulaire client."""
        checkin, checkout, guests, booking_type, separate = self._search_params(kw)
        ci = self._parse_date(checkin)
        co = self._parse_date(checkout)
        try:
            type_id = int(kw.get('type_id') or 0)
        except ValueError:
            type_id = 0
        room_type = self._site_types(booking_type or 'room').filtered(lambda t: t.id == type_id)
        proposal = {'rooms': request.env['hotel.room'].sudo().browse(),
                    'beds': request.env['hotel.bed'].sudo().browse(), 'floor': False}
        unit = total = 0.0
        valid = bool(room_type and booking_type and ci and co and co > ci)
        if valid:
            proposal = request.env['hotel.room'].sudo()._hotel_website_proposal(
                ci, co, guests, booking_type, room_type, separate)
            unit, total = self._type_price(room_type, ci, co, guests, booking_type)
        beds_by_room = [(room, proposal['beds'].filtered(lambda b, r=room: b.room_id == r))
                        for room in proposal['rooms']] if booking_type == 'bed' else []
        values = {
            'room_type': room_type,
            'valid': valid,
            'proposal': proposal,
            'beds_by_room': beds_by_room,
            'checkin': checkin,
            'checkout': checkout,
            'nights': (co - ci).days if valid else 0,
            'guests': guests,
            'booking_type': booking_type,
            'separate': separate,
            'unit': unit,
            'total': total,
            'currency': request.env.company.currency_id,
            'errors': [],
            'selected_room_id': 0,
            'selected_bed_ids': [],
            'last_name': '', 'first_name': '', 'birthdate': '', 'street': '',
            'city': '', 'email': '', 'phone': '', 'note': '',
            'birthdate_max': fields.Date.to_string(
                fields.Date.context_today(request.env.user) - relativedelta(years=18)),
            'today': self._today_str(),
        }
        values.update(extra)
        return values

    @http.route(['/hotel/book'], type='http', auth='public', website=True, sitemap=False)
    def hotel_book(self, **kw):
        values = self._book_values(kw)
        if not values['room_type']:
            return request.redirect('/hotel/rooms')
        return request.render('hotel_management.book_page', values)

    @http.route(['/hotel/room/<model("hotel.room"):room>'], type='http',
                auth='public', website=True, sitemap=False)
    def hotel_room_detail(self, room, **kw):
        """Fiche d'une chambre (présentation) ; la réservation se fait par la
        recherche (formules), le système proposant les chambres."""
        room = room.sudo()
        if not room.website_published:
            return request.redirect('/hotel/rooms')
        checkin, checkout, guests, booking_type, separate = self._search_params(kw)
        return request.render('hotel_management.room_detail_page', {
            'room': room, 'checkin': checkin, 'checkout': checkout, 'guests': guests,
            'booking_type': booking_type, 'today': self._today_str(),
        })

    def _website_booking_partner(self, last_name, first_name, email, phone,
                                 birthdate=None, street='', city=''):
        """Client de la réservation en ligne = la personne SAISIE dans le
        formulaire (jamais l'utilisateur connecté : un employé ou l'admin qui
        réserve pour un client ne doit pas se retrouver client). On reprend un
        contact existant seulement s'il a le même nom, le même prénom ET le
        même e-mail (hors contacts des utilisateurs internes) ; sinon un
        nouveau contact est créé."""
        Partner = request.env['res.partner'].sudo()
        internal_partners = request.env['res.users'].sudo().with_context(
            active_test=False).search([('share', '=', False)]).partner_id
        email_norm = email.strip().lower()
        candidates = request.env['hotel.reservation'].sudo()._find_homonym_partners(
            last_name, first_name).filtered(
            lambda p: (p.email or '').strip().lower() == email_norm
            and p not in internal_partners)
        values = {
            'phone': phone,
            'hotel_birthdate': birthdate,
            'street': street,
            'city': city,
        }
        if candidates:
            # Contact connu : on complète seulement ce qui manque sur sa fiche
            partner = candidates[0]
            missing = {k: v for k, v in values.items() if v and not partner[k]}
            if missing:
                partner.write(missing)
            return partner
        values = {k: v for k, v in values.items() if v}
        return Partner.create(dict(
            values, hotel_last_name=last_name, hotel_first_name=first_name, email=email))

    @http.route(['/hotel/booking/submit'], type='http', auth='public',
                website=True, methods=['POST'])
    def hotel_booking_submit(self, **post):
        """Envoi de la demande : la chambre / les lits choisis doivent faire
        partie des propositions du système pour la formule (recalculées ici :
        brouillons compris, chambres publiées seulement)."""
        if not post.get('type_id'):
            # ancien formulaire (sans formule) : type le moins cher du mode
            rtype = request.env['hotel.room.type'].sudo()._hotel_cheapest(
                self._booking_type(post) or 'room')
            post = dict(post, type_id=rtype.id, booking_type=self._booking_type(post) or 'room')
        values = self._book_values(post)
        room_type = values['room_type']
        booking_type = values['booking_type'] or 'room'
        guests = values['guests']
        proposal = values['proposal']
        ci = self._parse_date(values['checkin'])
        co = self._parse_date(values['checkout'])
        last_name = (post.get('last_name') or '').strip()
        first_name = (post.get('first_name') or '').strip()
        birthdate = self._parse_date(post.get('birthdate'))
        street = (post.get('street') or '').strip()
        city = (post.get('city') or '').strip()
        email = (post.get('email') or '').strip()
        phone = (post.get('phone') or '').strip()
        note = (post.get('note') or '').strip()
        try:
            room_id = int(post.get('room_id') or 0)
        except ValueError:
            room_id = 0
        bed_ids = [int(x) for x in request.httprequest.form.getlist('bed_ids') if x.isdigit()]
        Room = request.env['hotel.room'].sudo()
        Bed = request.env['hotel.bed'].sudo()
        room = Room.browse(room_id).exists().filtered('website_published')
        beds = Bed.browse(bed_ids).exists()

        errors = []
        if not room_type:
            errors.append("Formule introuvable.")
        if not (ci and co and co > ci):
            errors.append("Les dates de séjour sont invalides.")
        if not last_name:
            errors.append("Le nom est obligatoire.")
        if not first_name:
            errors.append("Le prénom est obligatoire.")
        if not birthdate:
            errors.append("La date de naissance est obligatoire.")
        else:
            today = fields.Date.context_today(request.env.user)
            if birthdate > today:
                errors.append("La date de naissance ne peut pas être dans le futur.")
            elif relativedelta(today, birthdate).years < 18:
                errors.append("La personne qui réserve doit avoir au moins 18 ans.")
        if not phone:
            errors.append("Le téléphone est obligatoire.")
        if not street:
            errors.append("L'adresse est obligatoire.")
        if not email:
            errors.append("L'adresse e-mail est obligatoire.")
        if room_type and ci and co and co > ci:
            if booking_type == 'bed':
                if not beds:
                    errors.append("Veuillez sélectionner vos lits.")
                elif beds - proposal['beds']:
                    errors.append(
                        "Lit(s) indisponible(s) ou non proposé(s) : %s. Choisissez parmi "
                        "les lits proposés." % ', '.join((beds - proposal['beds']).mapped('name')))
                elif len(beds) != guests:
                    errors.append(
                        "Vous êtes %s personne(s) : sélectionnez exactement %s lit(s)."
                        % (guests, guests))
                elif len(beds.room_id) > 1 and not values['separate']:
                    errors.append(
                        "Choisissez des lits dans une même chambre, ou cochez « J'accepte "
                        "d'être réparti dans des chambres différentes ».")
            else:
                if not room:
                    errors.append("Chambre introuvable.")
                elif room not in proposal['rooms']:
                    errors.append(
                        "La chambre %s n'est plus disponible pour cette formule : "
                        "choisissez parmi les chambres proposées." % room.name)

        if errors:
            values.update(
                errors=errors, last_name=last_name, first_name=first_name,
                birthdate=post.get('birthdate') or '', street=street, city=city,
                email=email, phone=phone, note=note, selected_room_id=room_id,
                selected_bed_ids=bed_ids)
            return request.render('hotel_management.book_page', values)

        partner = self._website_booking_partner(
            last_name, first_name, email, phone,
            birthdate=birthdate, street=street, city=city)
        if booking_type == 'bed':
            lines = [(0, 0, {'room_id': bed.room_id.id, 'bed_id': bed.id}) for bed in beds]
            floor = beds.room_id.floor_id[:1]
        else:
            lines = [(0, 0, {'room_id': room.id})]
            floor = room.floor_id
        reservation = request.env['hotel.reservation'].sudo().create({
            'partner_id': partner.id,
            'checkin': ci,
            'checkout': co,
            'guest_count': guests,
            'source': 'website',
            'booking_type': booking_type,
            'room_type_id': room_type.id,
            'floor_id': floor.id,
            'bed_placement': 'fill' if values['separate'] else 'together',
            'note': note,
            'line_ids': lines,
        })
        # Prix : tarif spécial client, sinon saison, sinon prix de la formule
        for line in reservation.line_ids:
            line._apply_price()
        # Réservation en ligne laissée en BROUILLON : l'hôtel la vérifie,
        # complète l'identité du client puis la confirme lui-même (bouton
        # Confirmer, puis « Envoyer confirmation » pour l'e-mail au client).
        # Le brouillon bloque déjà la chambre / les lits sur le site.
        # Le client reçoit tout de suite un e-mail « demande reçue ».
        try:
            reservation._send_request_received_mails()
        except Exception:
            _logger.exception("E-mail « demande reçue » non envoyé pour %s",
                              reservation.name)

        token = reservation._portal_ensure_token()
        return request.redirect('/hotel/booking/confirmation/%s?access_token=%s'
                                % (reservation.id, token))

    @http.route(['/hotel/booking/receipt/<int:reservation_id>'],
                type='http', auth='public', website=True, sitemap=False)
    def hotel_booking_receipt(self, reservation_id, access_token=None, **kw):
        """Reçu PDF (lien de l'e-mail client), protégé par le jeton d'accès."""
        reservation = request.env['hotel.reservation'].sudo().browse(
            reservation_id).exists()
        if not reservation or not access_token or not consteq(
                reservation.access_token or '', access_token):
            return request.redirect('/hotel/rooms')
        pdf, _type = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'hotel_management.action_report_hotel_reservation_receipt', reservation.ids)
        filename = 'Recu-%s.pdf' % reservation.name.replace('/', '-')
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', 'attachment; filename="%s"' % filename),
        ])

    @http.route(['/hotel/booking/confirmation/<int:reservation_id>'],
                type='http', auth='public', website=True, sitemap=False)
    def hotel_booking_confirmation(self, reservation_id, access_token=None, **kw):
        reservation = request.env['hotel.reservation'].sudo().browse(
            reservation_id).exists()
        # Jeton obligatoire : sans lui, n'importe qui pourrait afficher les
        # réservations des autres clients en changeant le numéro dans l'URL.
        if not reservation or not access_token or not consteq(
                reservation.access_token or '', access_token):
            return request.redirect('/hotel/rooms')
        return request.render('hotel_management.booking_confirmation_page', {
            'reservation': reservation,
        })
