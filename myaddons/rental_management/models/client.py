# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ============================================
    # PROFIL LOCATAIRE
    # ============================================
    is_tenant = fields.Boolean("Est Locataire", default=False)
    tenant_since = fields.Date("Client Depuis", default=fields.Date.today)

    # Documents
    id_card_number = fields.Char("N° CIN / Passeport")
    id_card_expiry = fields.Date("Expiration CIN")
    id_card_file = fields.Binary("Scan CIN")

    # Contact d'urgence
    emergency_contact = fields.Char("Contact Urgence")
    emergency_phone = fields.Char("Téléphone Urgence")

    # ============================================
    # STATISTIQUES LOCATION
    # ============================================
    rental_ids = fields.One2many('property.rental', 'client_id', string="Locations")
    rental_count = fields.Integer("Nombre de Locations", compute="_compute_rental_stats")
    active_rentals = fields.Integer("Locations Actives", compute="_compute_rental_stats")
    total_spent = fields.Float("Total Dépensé (DA)", compute="_compute_rental_stats")
    avg_rental_duration = fields.Float("Durée Moyenne (jours)", compute="_compute_rental_stats")

    # Fidélité
    loyalty_points = fields.Integer("Points Fidélité", default=0)
    loyalty_level = fields.Selection([
        ('bronze', '🥉 Bronze'),
        ('silver', '🥈 Argent'),
        ('gold', '🥇 Or'),
        ('platinum', '💎 Platine'),
    ], string="Niveau Fidélité", compute="_compute_loyalty", store=True)

    # Préférences
    preferred_type = fields.Selection([
        ('studio', 'Studio'),
        ('f1', 'F1'),
        ('f2', 'F2'),
        ('f3', 'F3'),
        ('f4', 'F4'),
    ], string="Type Préféré")
    preferred_block = fields.Char("Bloc Préféré")
    has_pets = fields.Boolean("A des Animaux")


    # Notes internes
    internal_notes = fields.Text("Notes Internes (confidentiel)")

    @api.depends('rental_ids', 'rental_ids.state')
    def _compute_rental_stats(self):
        for rec in self:
            rec.rental_count = len(rec.rental_ids)
            rec.active_rentals = len(rec.rental_ids.filtered(
                lambda r: r.state in ('confirmed', 'ongoing', 'expiring')
            ))
            rec.total_spent = sum(rec.rental_ids.filtered(
                lambda r: r.state == 'done'
            ).mapped('total_price'))

            durations = rec.rental_ids.mapped('duration_days')
            rec.avg_rental_duration = sum(durations) / len(durations) if durations else 0

    @api.depends('rental_count', 'total_spent')
    def _compute_loyalty(self):
        for rec in self:
            points = rec.rental_count * 10 + int(rec.total_spent / 1000)
            rec.loyalty_points = points

            if points >= 500:
                rec.loyalty_level = 'platinum'
            elif points >= 200:
                rec.loyalty_level = 'gold'
            elif points >= 50:
                rec.loyalty_level = 'silver'
            else:
                rec.loyalty_level = 'bronze'

    @api.depends('rental_ids', 'rental_ids.payment_status')
    def _compute_risk(self):
        for rec in self:
            if not rec.rental_ids:
                rec.risk_score = 0
                rec.risk_level = 'low'
                continue

            # Calculer le score de risque
            score = 0
            total = len(rec.rental_ids)

            # Retards de paiement
            late_payments = len(rec.rental_ids.filtered(lambda r: r.payment_status == 'unpaid'))
            score += (late_payments / total) * 50 if total else 0

            # Locations annulées
            cancelled = len(rec.rental_ids.filtered(lambda r: r.state == 'cancelled'))
            score += (cancelled / total) * 30 if total else 0

            # Dégâts
            damages = len(rec.rental_ids.filtered(lambda r: r.inspection_ids.filtered(lambda i: i.damage_found)))
            score += (damages / total) * 20 if total else 0

            rec.risk_score = min(int(score), 100)

            if score < 20:
                rec.risk_level = 'low'
            elif score < 50:
                rec.risk_level = 'medium'
            else:
                rec.risk_level = 'high'