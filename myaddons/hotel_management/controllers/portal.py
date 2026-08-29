# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class HotelCustomerPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'reservation_count' in counters:
            partner = request.env.user.partner_id
            values['reservation_count'] = request.env['hotel.reservation'].search_count(
                [('partner_id', '=', partner.id)])
        return values

    @http.route(['/my/reservations', '/my/reservations/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_reservations(self, page=1, **kw):
        Reservation = request.env['hotel.reservation']
        partner = request.env.user.partner_id
        domain = [('partner_id', '=', partner.id)]
        total = Reservation.search_count(domain)
        pager = portal_pager(
            url='/my/reservations', total=total, page=page, step=10)
        reservations = Reservation.search(
            domain, limit=10, offset=pager['offset'])
        values = {
            'reservations': reservations,
            'pager': pager,
            'page_name': 'reservation',
            'default_url': '/my/reservations',
        }
        return request.render('hotel_management.portal_my_reservations', values)

    @http.route(['/my/reservation/<int:reservation_id>'], type='http',
                auth='user', website=True)
    def portal_reservation_detail(self, reservation_id, **kw):
        try:
            reservation = request.env['hotel.reservation'].browse(reservation_id)
            reservation.check_access_rights('read')
            reservation.check_access_rule('read')
        except Exception:
            return request.redirect('/my')
        return request.render('hotel_management.portal_reservation_detail', {
            'reservation': reservation,
            'page_name': 'reservation',
        })
