# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class RentalPublicController(http.Controller):

    def _get_properties_data(self):
        # On récupère tous les appartements pour les afficher dans le formulaire
        return request.env['property.apartment'].sudo().search([])

    @http.route('/rental/form', type='http', auth='public', website=True)
    def rental_form(self, **kwargs):
        # On récupère le nom du succès s'il existe dans l'URL (via le redirect)
        success_name = kwargs.get('success_name')

        return request.render('rental_management.public_rental_form_pro', {
            'properties': self._get_properties_data(),
            'success': success_name and ("Félicitations ! Votre demande %s est enregistrée." % success_name) or None
        })

    @http.route('/rental/submit', type='http', auth='public', website=True, methods=['POST'])
    def rental_submit(self, **post):
        try:
            # 1. Gestion du partenaire (locataire)
            email = post.get('email')
            partner = request.env['res.partner'].sudo().search([('email', '=', email)], limit=1)

            if not partner:
                partner = request.env['res.partner'].sudo().create({
                    'name': post.get('name'),
                    'email': email,
                    'phone': post.get('phone'),
                })

            # 2. Création de l'enregistrement de location
            # On s'assure que property_id est bien présent
            property_id = post.get('property_id')
            if not property_id:
                raise Exception("Veuillez sélectionner un appartement.")

            rental = request.env['property.rental'].sudo().create({
                'property_id': int(property_id),
                'client_id': partner.id,
                'date_start': post.get('start_date'),
                'date_end': post.get('end_date'),
                'notes': post.get('message', ''),
            })

            # 3. LA CORRECTION : Redirection au lieu de render
            # Cela change l'URL et empêche le message de rester au rafraîchissement
            return request.redirect('/rental/form?success_name=%s' % rental.display_name)

        except Exception as e:
            # En cas d'erreur, on reste sur la page actuelle pour afficher l'erreur
            return request.render('rental_management.public_rental_form_pro', {
                'properties': self._get_properties_data(),
                'error': str(e)
            })