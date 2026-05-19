from odoo import models, fields, api


class CommercialRecuperation(models.Model):
    _name = 'commercial.recuperation'
    _description = 'Récupération'

    location_id = fields.Many2one(
        'commercial.location', string="Contrat", ondelete='cascade', required=True)
    responsable_id = fields.Many2one(
        'commercial.associe', string="Responsable")
    pourcentage = fields.Float(string="Pourcentage (%)")
    montant = fields.Float(
        string="Montant", compute='_compute_montant', store=True)

    @api.depends('pourcentage', 'location_id.net_encaisse')
    def _compute_montant(self):
        for rec in self:
            rec.montant = (rec.location_id.net_encaisse or 0) * (rec.pourcentage or 0) / 100
