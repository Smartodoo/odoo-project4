# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class RentalService(models.Model):
    _name = 'rental.service'
    _description = 'Prestation Additionnelle'
    _order = 'rental_id, sequence'

    rental_id = fields.Many2one('property.rental', string="Location", required=True)

    sequence = fields.Integer("Séquence", default=10)

    service_type = fields.Selection([
        ('cleaning', ' Ménage'),
        ('linen', ' Linge de Maison'),
        ('grocery', ' Courses'),
        ('other', ' Autre'),
    ], string="Type de Service", required=True)

    description = fields.Char("Description")

    # ============================================
    # PLANIFICATION
    # ============================================
    date = fields.Date("Date", default=fields.Date.context_today)
    frequency = fields.Selection([
        ('once', 'Une fois'),
        ('daily', 'Quotidien'),
        ('weekly', 'Hebdomadaire'),
        ('monthly', 'Mensuel'),
    ], string="Fréquence", default='once')

    # ============================================
    # TARIFICATION
    # ============================================
    unit_price = fields.Float("Prix Unitaire")
    quantity = fields.Float("Quantité", default=1.0)
    total = fields.Float("Total", compute="_compute_total", store=True)

    # ============================================
    # STATUT
    # ============================================
    state = fields.Selection([
        ('draft', ' Brouillon'),
        ('confirmed', '✅ Confirmé'),
        ('done', '🔒 Réalisé'),
        ('cancelled', '❌ Annulé'),
    ], string="État", default='draft')

    # Fournisseur / Prestataire
    provider_id = fields.Many2one('res.partner', string="Prestataire")

    notes = fields.Text("Notes")

    @api.depends('unit_price', 'quantity')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.unit_price * rec.quantity

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})