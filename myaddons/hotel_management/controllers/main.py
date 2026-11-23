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

    @http.route(['/hotel', '/hotel/rooms'], type='http', auth='public',
                website=True, sitemap=True)
    def hotel_rooms(self, **kw):
        Room = request.env['hotel.room'].sudo().with_context(hotel_include_draft=True)
        checkin = kw.get('checkin') or ''
        checkout = kw.get('checkout') or ''
        try:
            guests = max(int(kw.get('guests') or 1), 1)
        except ValueError:
            guests = 1
        booking_type = self._booking_type(kw)

        ci = self._parse_date(checkin)
        co = self._parse_date(checkout)
        error = None
        dates_selected = False
        available_rooms = Room.browse()
        occupied_rooms = Room.browse()
        published = [('website_published', '=', True)]
        rooms = Room.search(published)
        # Le type de location choisi filtre les chambres proposées
        if booking_type == 'bed':
            rooms = rooms.filtered(lambda r: r.rental_mode != 'room' and r.bed_count)
        elif booking_type == 'room':
            rooms = rooms.filtered(lambda r: r.rental_mode != 'bed')
        offers = {}

        if checkin or checkout:
            if ci and co and co > ci:
                dates_selected = True
                for r in rooms:
                    offers[r.id] = r.get_offer(ci, co, guests)
                if not booking_type:
                    error = ("Choisissez le type de location (chambre entière ou lit "
                             "en dortoir) pour voir les disponibilités.")
                    dates_selected = False
                elif booking_type == 'room':
                    # Par chambre : chambres libres en entier pouvant accueillir
                    # le groupe, de la capacité la plus proche à la plus grande.
                    fits = rooms.filtered(lambda r: offers[r.id]['whole'])
                    available_rooms = fits.sorted(
                        lambda r: (r.capacity, r.room_price, r.name or ''))
                    occupied_rooms = rooms - available_rooms
                else:
                    # Par lit : d'abord les chambres déjà partagées, du nombre de
                    # lits libres le plus proche du nombre de voyageurs au plus
                    # grand ; puis les chambres entièrement vides (même ordre).
                    offer = Room._hotel_bed_offer(ci, co, domain=published)
                    fits = [(room, free, partial) for room, free, partial in offer
                            if room in rooms and len(free) >= guests]
                    fits.sort(key=lambda f: (not f[2], len(f[1]), f[0].bed_price,
                                             f[0].name or ''))
                    available_rooms = Room.browse([room.id for room, _f, _p in fits])
                    for room, free, partial in fits:
                        offers[room.id]['partial'] = partial
                        offers[room.id]['free_count'] = len(free)
                    occupied_rooms = rooms - available_rooms
            else:
                error = "Veuillez saisir des dates valides (le départ doit suivre l'arrivée)."

        values = {
            'rooms': rooms,
            'available_rooms': available_rooms,
            'occupied_rooms': occupied_rooms,
            'offers': offers,
            'dates_selected': dates_selected,
            'checkin': checkin,
            'checkout': checkout,
            'guests': guests,
            'booking_type': booking_type,
            'error': error,
            'today': self._today_str(),
        }
        return request.render('hotel_management.rooms_page', values)

    def _booking_type(self, kw):
        """Type de location demandé : 'room' (chambre entière) ou 'bed' (lit en
        dortoir). Obligatoire pour une recherche avec dates ; '' = pas encore
        choisi (catalogue sans dates)."""
        value = kw.get('booking_type')
        return value if value in ('room', 'bed') else ''

    def _room_detail_values(self, room, checkin, checkout, guests, **extra):
        """Valeurs du template détail : dispo chambre entière + par lit."""
        ci = self._parse_date(checkin)
        co = self._parse_date(checkout)
        Bed = request.env['hotel.bed']
        # Comme au back-office : une réservation en brouillon bloque aussi
        room = room.with_context(hotel_include_draft=True) if room else room
        available = None
        whole_available = None
        free_beds = Bed
        dates_ok = bool(room and ci and co and co > ci)
        if dates_ok:
            whole_available = room.can_book_whole_room(ci, co)
            free_beds = room.bookable_beds(ci, co)
            available = bool(whole_available or free_beds)
        # Seuls les lits libres sur TOUTE la période sont proposés ; sans
        # dates, aucun lit n'est proposé (on demande d'abord les dates).
        beds_info = [{'bed': b, 'available': True} for b in free_beds]
        values = {
            'room': room,
            'checkin': checkin,
            'checkout': checkout,
            'guests': guests,
            'booking_type': '',
            'available': available,
            'whole_available': whole_available,
            'whole_price': room._get_whole_room_price(ci) if room else 0.0,
            'free_bed_count': len(free_beds),
            'beds_info': beds_info,
            'beds_need_dates': bool(room and room.rental_mode != 'room' and not dates_ok),
            'period_start': ci.strftime('%d/%m/%Y') if dates_ok else '',
            'period_end': co.strftime('%d/%m/%Y') if dates_ok else '',
            'errors': [],
            'last_name': '',
            'first_name': '',
            'birthdate': '',
            'street': '',
            'city': '',
            'birthdate_max': fields.Date.to_string(
                fields.Date.context_today(request.env.user) - relativedelta(years=18)),
            'email': '',
            'phone': '',
            'today': self._today_str(),
        }
        values.update(extra)
        return values

    @http.route(['/hotel/room/<model("hotel.room"):room>'], type='http',
                auth='public', website=True, sitemap=False)
    def hotel_room_detail(self, room, **kw):
        room = room.sudo().with_context(hotel_include_draft=True)
        if not room.website_published:
            return request.redirect('/hotel/rooms')
        checkin = kw.get('checkin') or ''
        checkout = kw.get('checkout') or ''
        try:
            guests = max(int(kw.get('guests') or 1), 1)
        except ValueError:
            guests = 1
        values = self._room_detail_values(
            room, checkin, checkout, guests,
            booking_type=kw.get('booking_type') if kw.get('booking_type') in ('room', 'bed') else '')
        return request.render('hotel_management.room_detail_page', values)

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
        # Brouillons compris : un lit / une chambre déjà retenu n'est pas revendu
        Room = request.env['hotel.room'].sudo().with_context(hotel_include_draft=True)
        try:
            room = Room.browse(int(post.get('room_id') or 0)).exists()
        except ValueError:
            room = Room.browse()
        ci = self._parse_date(post.get('checkin'))
        co = self._parse_date(post.get('checkout'))
        last_name = (post.get('last_name') or '').strip()
        first_name = (post.get('first_name') or '').strip()
        birthdate = self._parse_date(post.get('birthdate'))
        street = (post.get('street') or '').strip()
        city = (post.get('city') or '').strip()
        email = (post.get('email') or '').strip()
        phone = (post.get('phone') or '').strip()
        note = (post.get('note') or '').strip()
        try:
            guests = max(int(post.get('guests') or 1), 1)
        except ValueError:
            guests = 1

        # Type de réservation : chambre entière ou lit(s)
        booking_type = post.get('booking_type') or 'room'
        bed_ids_raw = request.httprequest.form.getlist('bed_ids')
        bed_ids = [int(x) for x in bed_ids_raw if x.isdigit()]
        beds = request.env['hotel.bed'].sudo().with_context(
            hotel_include_draft=True).browse(bed_ids).exists()
        if room:
            beds = beds.filtered(lambda b: b.room_id == room)
        # Le mode de location de la chambre prime sur le choix du formulaire
        if room.rental_mode == 'bed':
            booking_type = 'bed'
        elif room.rental_mode == 'room':
            booking_type = 'room'
        # Tous les lits de la chambre = chambre entière (sauf dortoir)
        if booking_type == 'bed' and room and room.rental_mode == 'both' \
                and room.bed_ids and set(beds.ids) >= set(room.bed_ids.ids):
            booking_type = 'room'
            beds = request.env['hotel.bed'].sudo().browse()

        errors = []
        if not room:
            errors.append("Chambre introuvable.")
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
        if room and ci and co and co > ci:
            if booking_type == 'bed':
                if not beds:
                    errors.append("Veuillez sélectionner au moins un lit.")
                else:
                    unavailable = beds.filtered(lambda b: not b.is_available(ci, co))
                    if unavailable:
                        errors.append(
                            "Lit(s) indisponible(s) sur la période : %s."
                            % ', '.join(unavailable.mapped('name')))
                    if guests != len(beds):
                        errors.append(
                            "Vous êtes %s personne(s) : sélectionnez exactement %s lit(s)."
                            % (guests, guests))
            else:
                room_places = room.capacity or len(room.bed_ids.filtered('active'))
                if guests > room_places:
                    errors.append(
                        "Cette chambre accueille au maximum %s personne(s)." % room_places)
                if not room.can_book_whole_room(ci, co):
                    free = room.bookable_beds(ci, co)
                    if free:
                        errors.append(
                            "La chambre entière n'est plus disponible (des lits sont déjà "
                            "loués), mais %s lit(s) restent libres : réservez-les au lit."
                            % len(free))
                    else:
                        errors.append(
                            "Cette chambre n'est plus disponible sur la période choisie.")

        if errors:
            values = self._room_detail_values(
                room, post.get('checkin') or '', post.get('checkout') or '',
                guests, errors=errors, last_name=last_name,
                first_name=first_name, birthdate=post.get('birthdate') or '',
                street=street, city=city, email=email, phone=phone,
                booking_type=post.get('booking_type') or '')
            return request.render('hotel_management.room_detail_page', values)

        partner = self._website_booking_partner(
            last_name, first_name, email, phone,
            birthdate=birthdate, street=street, city=city)

        # Prix : tarif spécial client, sinon tarifs saisonniers nuit par nuit
        unit = room._get_stay_unit_price(ci, co, booking_type, partner)
        if booking_type == 'bed' and beds:
            # Par lit : une ligne par lit (la chambre est déduite du lit)
            lines = [(0, 0, {'room_id': room.id, 'bed_id': bed.id, 'price_unit': unit})
                     for bed in beds]
        else:
            lines = [(0, 0, {'room_id': room.id, 'price_unit': unit})]

        reservation = request.env['hotel.reservation'].sudo().create({
            'partner_id': partner.id,
            'checkin': ci,
            'checkout': co,
            'guest_count': guests,
            'source': 'website',
            'booking_type': booking_type,
            'note': note,
            'line_ids': lines,
        })
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
