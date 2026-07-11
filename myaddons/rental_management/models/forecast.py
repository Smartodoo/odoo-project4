# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime, timedelta


#class RentalForecast(models.Model):
 #   _name = 'rental.forecast'
  #  _description = 'Prévision de Revenus'
   # _order = 'month'

    #month = fields.Date("Mois", required=True)

    # Données réelles (après coup)
    #actual_occupancy = fields.Float("Occupation Réelle (%)")
   # actual_revenue = fields.Float("Revenu Réel (DA)")

    # Prévisions
    #predicted_occupancy = fields.Float("Occupation Prédite (%)")
    #predicted_revenue = fields.Float("Revenu Prédit (DA)")

    # Variance
   # variance = fields.Float("Écart (%)", compute="_compute_variance")
    #variance_amount = fields.Float("Écart (DA)", compute="_compute_variance")

    # Analyse
   # trend = fields.Selection([
    #    ('up', '📈 Hausse'),
     #   ('stable', '➡️ Stable'),
      #  ('down', '📉 Baisse'),
    #], string="Tendance", compute="_compute_trend")

    #@api.depends('actual_revenue', 'predicted_revenue')
    #def _compute_variance(self):
     #   for rec in self:
      #      if rec.predicted_revenue > 0:
       #         rec.variance = ((rec.actual_revenue - rec.predicted_revenue) / rec.predicted_revenue) * 100
        #        rec.variance_amount = rec.actual_revenue - rec.predicted_revenue
         #   else:
          #      rec.variance = 0
           #     rec.variance_amount = 0

    #@api.depends('predicted_revenue')
   # def _compute_trend(self):
    #    for rec in self:
            # Comparer avec le mois précédent
     #       previous = self.search([
      #          ('month', '<', rec.month),
       #     ], order='month desc', limit=1)

        #    if previous:
         #       if rec.predicted_revenue > previous.predicted_revenue * 1.05:
          #          rec.trend = 'up'
           #     elif rec.predicted_revenue < previous.predicted_revenue * 0.95:
            #        rec.trend = 'down'
             #   else:
              #      rec.trend = 'stable'
            #else:
             #   rec.trend = 'stable'

    #@api.model
   # def generate_forecast(self, months_ahead=6):
    #    """Génère les prévisions pour les mois à venir"""
     #   today = fields.Date.today()

      #  for i in range(months_ahead):
       #     month_date = today.replace(day=1) + timedelta(days=32 * i)
        #    month_date = month_date.replace(day=1)

            # Analyser l'historique des 3 dernières années pour ce mois
         #   historical = self.search([
          #      ('month', '>=', month_date.replace(year=month_date.year - 3)),
           #     ('month', '<', month_date),
            #    ('actual_revenue', '>', 0),
           # ])

            #if historical:
             #   avg_revenue = sum(historical.mapped('actual_revenue')) / len(historical)
              #  avg_occupancy = sum(historical.mapped('actual_occupancy')) / len(historical)
            #else:
             #   avg_revenue = 0
              #  avg_occupancy = 0

            # Créer ou mettre à jour la prévision
            #forecast = self.search([('month', '=', month_date)], limit=1)
            #vals = {
             #   'predicted_revenue': avg_revenue,
              #  'predicted_occupancy': avg_occupancy,
            #}

            #if forecast:
             #   forecast.write(vals)
            #else:
             #   vals['month'] = month_date
              #  self.create(vals)

        #return True