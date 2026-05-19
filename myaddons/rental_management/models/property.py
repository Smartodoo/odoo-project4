# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class PropertyApartment(models.Model):
    _name = 'property.apartment'
    _description = 'Appartement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'

    # ═══════════════════════════════════════════════════════════════
    # IDENTIFICATION
    # ═══════════════════════════════════════════════════════════════
    name = fields.Char("Référence", required=True, tracking=True)
    image = fields.Binary("Photo Principale", attachment=True)
    image_ids = fields.Many2many('ir.attachment', string="Galerie Photos")
    active = fields.Boolean("Actif", default=True)

    # ═══════════════════════════════════════════════════════════════
    # TYPE & LOCALISATION
    # ═══════════════════════════════════════════════════════════════
    type = fields.Selection([
        ('studio', 'Studio'), ('f1', 'F1'), ('f2', 'F2'),
        ('f3', 'F3'), ('f4', 'F4'), ('villa', 'Villa'),
    ], string="Type", required=True, default='studio', tracking=True)
    address = fields.Char("Adresse Complète")
    block = fields.Char("Bloc / Bâtiment")
    floor = fields.Integer("Étage")
    door_number = fields.Char("N° Porte")
    latitude = fields.Float("Latitude")
    longitude = fields.Float("Longitude")

    # ═══════════════════════════════════════════════════════════════
    # CARACTÉRISTIQUES
    # ═══════════════════════════════════════════════════════════════
    surface = fields.Float("Surface (m²)")
    bedrooms = fields.Integer("Chambres", compute="_compute_rooms", store=True)
    bathrooms = fields.Integer("Salles de Bain", default=1)
    capacity = fields.Integer("Capacité", default=2)
    is_furnished = fields.Boolean("Meublé")
    has_wifi = fields.Boolean("Wi-Fi")
    has_ac = fields.Boolean("Climatisation")
    has_parking = fields.Boolean("Parking")
    has_elevator = fields.Boolean("Ascenseur")
    has_balcony = fields.Boolean("Balcon")
    has_washing = fields.Boolean("Machine à Laver")
    has_kitchen = fields.Boolean("Cuisine Équipée")
    has_tv = fields.Boolean("TV")
    comfort_score = fields.Integer("Score Confort", compute="_compute_comfort_score", store=True)

    # ═══════════════════════════════════════════════════════════════
    # TARIFICATION
    # ═══════════════════════════════════════════════════════════════
    price_day = fields.Float("Tarif Jour (DA)")
    price_week = fields.Float("Tarif Semaine (DA)")
    price_month = fields.Float("Tarif Mois (DA)")
    price_year = fields.Float("Tarif An (DA)")
    avg_daily_rate = fields.Float("Moyenne Jour", compute="_compute_avg_rate")

    # ═══════════════════════════════════════════════════════════════
    # STATUT & RELATIONS
    # ═══════════════════════════════════════════════════════════════
    state = fields.Selection([
        ('available', '🟢 Disponible'),
        ('occupied', '🔴 Loué'),
        ('soon', '🟠 Bientôt Libre'),
        ('maintenance', '🔧 En Maintenance'),
        ('cleaning', '🧹 En Ménage'),
        ('reserved', '🔵 Réservé'),
    ], string="Statut", default='available', tracking=True)

    rental_ids = fields.One2many('property.rental', 'property_id', string="Locations")
    maintenance_ids = fields.One2many('property.maintenance', 'apartment_id', string="Maintenances")
    color = fields.Integer("Couleur", compute="_compute_color", store=True)

    # STATS KANBAN
    total_rentals = fields.Integer("Total Locations", compute="_compute_stats")
    total_revenue = fields.Float("Revenu Total", compute="_compute_stats")
    avg_occupancy = fields.Float("Occupation Moyenne", compute="_compute_stats")

    # ═══════════════════════════════════════════════════════════════
    # --- CALCULS (COMPUTE & ONCHANGE) ---
    # ═══════════════════════════════════════════════════════════════

    @api.onchange('price_day')
    def _onchange_price_day(self):
        """ Calcule automatiquement les tarifs mensuels et annuels basés sur le prix jour """
        if self.price_day:
            self.price_month = self.price_day * 30
            self.price_year = self.price_day * 365

    @api.depends('rental_ids')
    def _compute_stats(self):
        for rec in self:
            rec.total_rentals = len(rec.rental_ids)
            rec.total_revenue = sum(rec.rental_ids.mapped('total_price')) if rec.rental_ids else 0
            rec.avg_occupancy = 0

    @api.depends('type')
    def _compute_rooms(self):
        mapping = {'studio': 1, 'f1': 1, 'f2': 2, 'f3': 3, 'f4': 4, 'villa': 5}
        for rec in self:
            rec.bedrooms = mapping.get(rec.type, 0)

    @api.depends('is_furnished', 'has_wifi', 'has_ac', 'has_parking', 'has_elevator', 'has_balcony', 'has_washing',
                 'has_kitchen', 'has_tv')
    def _compute_comfort_score(self):
        for rec in self:
            score = 0
            if rec.is_furnished: score += 15
            if rec.has_wifi: score += 10
            if rec.has_ac: score += 10
            if rec.has_parking: score += 10
            if rec.has_elevator: score += 5
            if rec.has_balcony: score += 10
            if rec.has_washing: score += 10
            if rec.has_kitchen: score += 15
            if rec.has_tv: score += 15
            rec.comfort_score = min(score, 100)

    @api.depends('price_day', 'price_week', 'price_month', 'price_year')
    def _compute_avg_rate(self):
        for rec in self:
            rates = [r for r in [rec.price_day, rec.price_week / 7, rec.price_month / 30, rec.price_year / 365] if
                     r > 0]
            rec.avg_daily_rate = sum(rates) / len(rates) if rates else 0

    @api.depends('state')
    def _compute_color(self):
        colors = {'available': 10, 'occupied': 1, 'soon': 3, 'maintenance': 4, 'cleaning': 5, 'reserved': 9}
        for rec in self:
            rec.color = colors.get(rec.state, 0)

    # ═══════════════════════════════════════════════════════════════
    # --- ACTIONS ---
    # ═══════════════════════════════════════════════════════════════
    def action_set_available(self):
        self.write({'state': 'available'})

    def action_set_maintenance(self):
        self.write({'state': 'maintenance'})

    def action_set_cleaning(self):
        self.write({'state': 'cleaning'})

    def action_rent_now(self):
        self.ensure_one()
        return {
            'name': _('Nouvelle Location'),
            'type': 'ir.actions.act_window',
            'res_model': 'property.rental',
            'view_mode': 'form',
            'context': {'default_property_id': self.id},
            'target': 'current',
        }

    def action_view_history(self):
        self.ensure_one()
        return {
            'name': _('Historique des Locations'),
            'type': 'ir.actions.act_window',
            'res_model': 'property.rental',
            'view_mode': 'tree,form',
            'domain': [('property_id', '=', self.id)],
        }

    def action_view_revenue(self):
        self.ensure_one()
        return self.action_view_history()

    def action_create_maintenance(self):
        self.ensure_one()
        return {
            'name': _('Nouvelle Maintenance'),
            'type': 'ir.actions.act_window',
            'res_model': 'property.maintenance',
            'view_mode': 'form',
            'context': {'default_apartment_id': self.id},
            'target': 'new',
        }

    _sql_constraints = [('name_uniq', 'unique(name)', 'La référence doit être unique !')]