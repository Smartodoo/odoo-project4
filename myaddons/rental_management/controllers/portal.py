# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal

class RentalPortalController(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        """ Ajoute le compteur de locations sur la page d'accueil du portail """
        values = super(RentalPortalController, self)._prepare_home_portal_values(counters)
        if 'rental_count' in counters:
            values['rental_count'] = request.env['property.rental'].sudo().search_count([
                ('client_id', '=', request.env.user.partner_id.id)
            ])
        return values

    @http.route(['/my/rentals'], type='http', auth="user", website=True)
    def portal_my_rentals(self, **kw):
        """ Affiche la liste des locations de l'utilisateur """
        partner = request.env.user.partner_id
        rentals = request.env['property.rental'].sudo().search([('client_id', '=', partner.id)])
        return request.render("rental_management.portal_my_rentals", {
            'rentals': rentals,
            'page_name': 'my_rentals',
        })