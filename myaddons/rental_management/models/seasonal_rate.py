# -*- coding: utf-8 -*-
from odoo import models, fields, api


class PropertySeasonalRate(models.Model):
    _name = 'property.seasonal.rate'
    _description = 'Tarif Saisonnier'
    _order = 'date_start'

    apartment_id = fields.Many2one('property.apartment', string="Appartement", required=True)

    season_name = fields.Char("Nom de la Saison", required=True)
    date_start = fields.Date("Date Début", required=True)
    date_end = fields.Date("Date Fin", required=True)

    # Ajustement de prix en pourcentage
    price_adjustment = fields.Float("Ajustement (%)", default=0.0,
                                    help="Ex: +30 pour +30%, -10 pour -10%")

    # Prix minimum garanti
    min_price_day = fields.Float("Prix Journalier Minimum")
    min_price_month = fields.Float("Prix Mensuel Minimum")

    is_active = fields.Boolean("Active", default=True)
    color = fields.Integer("Couleur", default=0)

    # Description pour le client
    description = fields.Text("Description (visible client)")

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_end <= rec.date_start:
                raise models.ValidationError("La date fin doit être après la date début !")

    @api.constrains('date_start', 'date_end', 'apartment_id')
    def _check_overlap(self):
        for rec in self:
            overlapping = self.search([
                ('id', '!=', rec.id),
                ('apartment_id', '=', rec.apartment_id.id),
                ('is_active', '=', True),
                ('date_start', '<=', rec.date_end),
                ('date_end', '>=', rec.date_start),
            ])
            if overlapping:
                raise models.ValidationError("Cette période chevauche une autre saison active !")