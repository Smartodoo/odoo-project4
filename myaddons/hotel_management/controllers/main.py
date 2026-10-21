# -*- coding: utf-8 -*-
from odoo import fields, http
from odoo.http import request


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
        Room = request.env['hotel.room'].sudo()
        checkin = kw.get('checkin') or ''
        checkout = kw.get('checkout') or ''
        try:
            guests = max(int(kw.get('guests') or 1), 1)
        except ValueError:
            guests = 1

        ci = self._parse_date(checkin)
        co = self._parse_date(checkout)
        error = None
        dates_selected = False
        available_rooms = Room.browse()
        occupied_rooms = Room.browse()
        rooms = Room.search([('website_published', '=', True)])

        if checkin or checkout:
            if ci and co and co > ci:
                dates_selected = True
                avail_ids, occ_ids = [], []
                for r in rooms:
                    if r.capacity >= guests and r.is_available(ci, co):
                        avail_ids.append(r.id)
                    else:
                        occ_ids.append(r.id)
                available_rooms = Room.browse(avail_ids)
                occupied_rooms = Room.browse(occ_ids)
            else:
                error = "Veuillez saisir des dates valides (le départ doit suivre l'arrivée)."

        values = {
            'rooms': rooms,
            'available_rooms': available_rooms,
            'occupied_rooms': occupied_rooms,
            'dates_selected': dates_selected,
            'checkin': checkin,
            'checkout': checkout,
            'guests': guests,
            'error': error,
            'today': self._today_str(),
        }
        return request.render('hotel_management.rooms_page', values)

    def _room_detail_values(self, room, checkin, checkout, guests, **extra):
        """Valeurs du template détail : dispo chambre entière + par lit."""
        ci = self._parse_date(checkin)
        co = self._parse_date(checkout)
        beds = room.bed_ids.filtered('active') if room else request.env['hotel.bed']
        available = None
        bed_av = {}
        if room and ci and co and co > ci:
            available = room.is_available(ci, co)
            for b in beds:
                bed_av[b.id] = b.is_available(ci, co)
        beds_info = [{'bed': b, 'available': bed_av.get(b.id)} for b in beds]
        values = {
            'room': room,
            'checkin': checkin,
            'checkout': checkout,
            'guests': guests,
            'available': available,
            'beds_info': beds_info,
            'errors': [],
            'name': '',
            'email': '',
            'phone': '',
            'today': self._today_str(),
        }
        values.update(extra)
        return values

    @http.route(['/hotel/room/<model("hotel.room"):room>'], type='http',
                auth='public', website=True, sitemap=False)
    def hotel_room_detail(self, room, **kw):
        room = room.sudo()
        if not room.website_published:
            return request.redirect('/hotel/rooms')
        checkin = kw.get('checkin') or ''
        checkout = kw.get('checkout') or ''
        try:
            guests = max(int(kw.get('guests') or 1), 1)
        except ValueError:
            guests = 1
        values = self._room_detail_values(room, checkin, checkout, guests)
        return request.render('hotel_management.room_detail_page', values)

    @http.route(['/hotel/booking/submit'], type='http', auth='public',
                website=True, methods=['POST'])
    def hotel_booking_submit(self, **post):
        Room = request.env['hotel.room'].sudo()
        try:
            room = Room.browse(int(post.get('room_id') or 0)).exists()
        except ValueError:
            room = Room.browse()
        ci = self._parse_date(post.get('checkin'))
        co = self._parse_date(post.get('checkout'))
        name = (post.get('name') or '').strip()
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
        beds = request.env['hotel.bed'].sudo().browse(bed_ids).exists()
        if room:
            beds = beds.filtered(lambda b: b.room_id == room)
        # Tous les lits de la chambre = chambre entière
        if booking_type == 'bed' and room and room.bed_ids \
                and set(beds.ids) >= set(room.bed_ids.ids):
            booking_type = 'room'
            beds = request.env['hotel.bed'].sudo().browse()

        errors = []
        if not room:
            errors.append("Chambre introuvable.")
        if not (ci and co and co > ci):
            errors.append("Les dates de séjour sont invalides.")
        if not name:
            errors.append("Le nom est obligatoire.")
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
            elif not room.is_available(ci, co):
                errors.append("Cette chambre n'est plus disponible sur la période choisie.")

        if errors:
            values = self._room_detail_values(
                room, post.get('checkin') or '', post.get('checkout') or '',
                guests, errors=errors, name=name, email=email, phone=phone)
            return request.render('hotel_management.room_detail_page', values)

        # Client : utilisateur connecté, sinon existant par e-mail, sinon création
        partner = False
        if not request.env.user._is_public():
            partner = request.env.user.partner_id
        if not partner:
            partner = request.env['res.partner'].sudo().search(
                [('email', '=', email)], limit=1)
        if not partner:
            partner = request.env['res.partner'].sudo().create({
                'name': name, 'email': email, 'phone': phone,
            })

        if booking_type == 'bed' and beds:
            line_vals = {
                'room_id': room.id,
                'booking_type': 'bed',
                'bed_ids': [(6, 0, beds.ids)],
                'price_unit': sum(beds.mapped('price')),
            }
        else:
            line_vals = {
                'room_id': room.id,
                'booking_type': 'room',
                'price_unit': room._get_price_for_date(ci),
            }

        reservation = request.env['hotel.reservation'].sudo().create({
            'partner_id': partner.id,
            'checkin': ci,
            'checkout': co,
            'adults': guests,
            'source': 'website',
            'note': note,
            'line_ids': [(0, 0, line_vals)],
        })
        try:
            reservation.action_confirm()
        except Exception:
            # En cas de conflit de dernière minute, on laisse en brouillon
            # pour traitement manuel par l'hôtel.
            pass
        try:
            reservation.action_send_confirmation()
        except Exception:
            pass

        return request.redirect('/hotel/booking/confirmation/%s' % reservation.id)

    @http.route(['/hotel/booking/confirmation/<int:reservation_id>'],
                type='http', auth='public', website=True, sitemap=False)
    def hotel_booking_confirmation(self, reservation_id, **kw):
        reservation = request.env['hotel.reservation'].sudo().browse(
            reservation_id).exists()
        if not reservation:
            return request.redirect('/hotel/rooms')
        return request.render('hotel_management.booking_confirmation_page', {
            'reservation': reservation,
        })
