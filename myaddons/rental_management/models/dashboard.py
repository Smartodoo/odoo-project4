# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime, timedelta
import json


class RentalDashboard(models.Model):
    _name = 'rental.dashboard'
    _description = 'Tableau de Bord Location'

    # ============================================
    # KPIs APPARTEMENTS
    # ============================================
    total_apartments = fields.Integer("Total", compute="_compute_kpi")
    available_count = fields.Integer("Disponibles", compute="_compute_kpi")
    occupied_count = fields.Integer("Occupés", compute="_compute_kpi")
    soon_count = fields.Integer("Bientôt Libre", compute="_compute_kpi")
    maintenance_count = fields.Integer("Maintenance", compute="_compute_kpi")
    cleaning_count = fields.Integer("Ménage", compute="_compute_kpi")

    # ============================================
    # TAUX & REVENUS
    # ============================================
    occupancy_rate = fields.Float("Taux Occupation (%)", compute="_compute_kpi")

    daily_revenue = fields.Float("Aujourd'hui", compute="_compute_revenue")
    weekly_revenue = fields.Float("Cette Semaine", compute="_compute_revenue")
    monthly_revenue = fields.Float("Ce Mois", compute="_compute_revenue")
    yearly_revenue = fields.Float("Cette Année", compute="_compute_revenue")

    # ============================================
    # ALERTES
    # ============================================
    expiring_rentals = fields.One2many('property.rental', compute="_compute_alerts", string="Expirantes")
    unpaid_rentals = fields.One2many('property.rental', compute="_compute_alerts", string="Impayées")
    active_maintenances = fields.One2many('property.maintenance', compute="_compute_alerts", string="Maintenances")

    dashboard_graph_data = fields.Text(compute='_compute_graph_data')
    graph_revenue = fields.Text(compute='_compute_graph_revenue')

    def _compute_graph_data(self):
        # Ici, on prépare une liste de revenus par mois pour le graphique
        for rec in self:
            # Exemple de structure simple pour commencer
            rec.dashboard_graph_data = json.dumps([{
                'values': [{'label': 'Jan', 'value': 1000}, {'label': 'Fev', 'value': 2000}],
                'key': 'Revenus Mensuels',
            }])

    def _compute_graph_revenue(self):
        for rec in self:
            # On crée une structure JSON complète qu'Odoo 17 attend
            data = [{
                "values": [
                    {"label": "Mars", "value": 150000},
                    {"label": "Avril", "value": 317166}
                ],
                "key": "Revenus Mensuels",
                "area": True,
                "color": "#2DC071",
            }]

            # On ajoute le type de graphique directement dans le dictionnaire final
            # C'est ce 'graph_type' qui va régler l'erreur Owl
            rec.graph_revenue = json.dumps({
                'data': data,
                'graph_type': 'bar',  # OU 'line' selon ta préférence
            })

    @api.depends()
    def _compute_kpi(self):
        today = fields.Date.today()
        soon_limit = today + timedelta(days=30)  # On définit la limite de 30 jours

        for rec in self:
            apartments = self.env['property.apartment'].search([])
            rec.total_apartments = len(apartments)
            rec.available_count = len(apartments.filtered(lambda a: a.state == 'available'))
            rec.occupied_count = len(apartments.filtered(lambda a: a.state == 'occupied'))

            # MODIFICATION ICI : On compte les locations qui finissent dans les 30 jours
            soon_rentals = self.env['property.rental'].search([
                ('state', '=', 'ongoing'),
                ('date_end', '>=', today),
                ('date_end', '<=', soon_limit)
            ])
            rec.soon_count = len(soon_rentals.mapped('property_id'))

            rec.maintenance_count = len(apartments.filtered(lambda a: a.state == 'maintenance'))
            rec.cleaning_count = len(apartments.filtered(lambda a: a.state == 'cleaning'))

            total = rec.total_apartments or 1
            rec.occupancy_rate = round((rec.occupied_count / total) * 100, 2)

    @api.depends()
    def _compute_revenue(self):
        today = fields.Date.today()
        # On définit strictement les périodes
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        for rec in self:
            # On cherche les locations validées
            rentals = self.env['property.rental'].search([('state', 'in', ('ongoing', 'confirmed'))])

            # 1. AUJOURD'HUI : Uniquement celles commencées AUJOURD'HUI
            rec.daily_revenue = sum(rentals.filtered(lambda r: r.date_start == today).mapped('total_price'))

            # 2. CETTE SEMAINE : Somme de la semaine (inclut aujourd'hui)
            rec.weekly_revenue = sum(
                rentals.filtered(lambda r: week_start <= r.date_start <= today).mapped('total_price'))

            # 3. CE MOIS : Somme du mois (inclut la semaine)
            rec.monthly_revenue = sum(
                rentals.filtered(lambda r: month_start <= r.date_start <= today).mapped('total_price'))

            # 4. CETTE ANNÉE : Somme totale de l'année 2026
            rec.yearly_revenue = sum(
                rentals.filtered(lambda r: year_start <= r.date_start <= today).mapped('total_price'))

    @api.depends()
    def _compute_alerts(self):
        today = fields.Date.today()
        for rec in self:
            rec.expiring_rentals = self.env['property.rental'].search([
                ('state', 'in', ('ongoing', 'expiring')),
                ('date_end', '<=', today + timedelta(days=30)),
                ('date_end', '>=', today),  # Ajoute ceci pour ne voir que le futur
            ])

            rec.unpaid_rentals = self.env['property.rental'].search([
                ('state', 'in', ('confirmed', 'ongoing', 'expiring')),
                ('payment_status', 'in', ('unpaid', 'partial')),
            ])

            rec.active_maintenances = self.env['property.maintenance'].search([
                ('state', 'in', ('new', 'confirmed', 'in_progress', 'waiting_parts')),
            ])

    def action_refresh(self):
        return {'type': 'ir.actions.client', 'tag': 'reload'}