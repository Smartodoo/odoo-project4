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
        ci = self._parse_date(checkin)
        co = self._parse_date(checkout)
        available = None
        if ci and co and co > ci:
            available = room.is_available(ci, co)
        values = {
            'room': room,
            'checkin': checkin,
            'checkout': checkout,
            'guests': guests,
            'available': available,
            'errors': [],
            'name': '',
            'email': '',
            'phone': '',
            'today': self._today_str(),
        }
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

        errors = []
        if not room:
            errors.append("Chambre introuvable.")
        if not (ci and co and co > ci):
            errors.append("Les dates de séjour sont invalides.")
        if not name:
            errors.append("Le nom est obligatoire.")
        if not email:
            errors.append("L'adresse e-mail est obligatoire.")
        if room and ci and co and co > ci and not room.is_available(ci, co):
            errors.append("Cette chambre n'est plus disponible sur la période choisie.")

        if errors:
            values = {
                'room': room,
                'checkin': post.get('checkin') or '',
                'checkout': post.get('checkout') or '',
                'guests': guests,
                'available': None,
                'errors': errors,
                'name': name,
                'email': email,
                'phone': phone,
                'today': self._today_str(),
            }
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

        reservation = request.env['hotel.reservation'].sudo().create({
            'partner_id': partner.id,
            'checkin': ci,
            'checkout': co,
            'adults': guests,
            'source': 'website',
            'note': note,
            'line_ids': [(0, 0, {
                'room_id': room.id,
                'price_unit': room._get_price_for_date(ci),
            })],
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
