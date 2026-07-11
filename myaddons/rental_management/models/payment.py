# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class RentalPayment(models.Model):
    _name = 'rental.payment'
    _description = 'Paiement Location'
    _inherit = ['mail.thread']
    _order = 'date desc'

    name = fields.Char("N° Paiement", readonly=True, default="/", copy=False)

    rental_id = fields.Many2one('property.rental', string="Location", required=True)
    apartment_id = fields.Many2one('property.apartment', string="Appartement",
                                   related='rental_id.property_id', store=True)
    client_id = fields.Many2one('res.partner', string="Client",
                                related='rental_id.client_id', store=True)

    # ============================================
    # DÉTAILS PAIEMENT
    # ============================================
    date = fields.Date("Date Paiement", default=fields.Date.context_today, required=True)
    amount = fields.Float("Montant", required=True)

    payment_method = fields.Selection([
        ('cash', 'Espèces'),
        ('bank_transfer', ' Virement Bancaire'),
        ('check', 'Chèque'),
        ('card', ' Carte Bancaire'),
        ('mobile', 'Paiement Mobile'),
    ], string="Méthode", default='cash', required=True)

    reference = fields.Char("Référence / N° Transaction")

    # ============================================
    # TYPE DE PAIEMENT
    # ============================================
    payment_type = fields.Selection([
        ('deposit', 'Caution'),
        ('rent', ' Loyer'),
        ('service', 'Service'),
        ('penalty', ' Pénalité'),
        ('refund', ' Remboursement'),
    ], string="Type", default='rent', required=True)

    # ============================================
    # STATUT
    # ============================================
    state = fields.Selection([
        ('draft', ' Brouillon'),
        ('confirmed', '✅ Confirmé'),
        ('cancelled', '❌ Annulé'),
    ], string="État", default='draft')

    # ============================================
    # NOTES
    # ============================================
    notes = fields.Text("Notes")

    # ============================================
    # RELANCE
    # ============================================
    is_reminder_sent = fields.Boolean("Relance Envoyée", default=False)
    reminder_date = fields.Date("Date Relance")

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('rental.payment') or 'PAY/NEW'
        return super(RentalPayment, self).create(vals)

    def action_confirm(self):
        # On passe tout le monde en confirmé d'un coup (plus rapide)
        self.write({'state': 'confirmed'})

        for rec in self:
            if rec.payment_type == 'rent' and rec.rental_id:
                # On ajoute le montant au cumul de la location
                rec.rental_id.amount_paid += rec.amount

                # On poste un message automatique sur la fiche de location
                rec.rental_id.message_post(
                    body=_("💰 Paiement reçu : <b>%s DA</b><br/>Méthode : %s") % (
                        rec.amount,
                        dict(self._fields['payment_method'].selection).get(rec.payment_method)
                    )
                )
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        # Rembourser le montant
        for rec in self:
            if rec.payment_type == 'rent':
                rec.rental_id.amount_paid -= rec.amount

    def action_send_reminder(self):
        """Simulation de relance de paiement avec notification"""
        for rec in self:
            # On enregistre quand même que la relance a été "faite"
            rec.write({
                'is_reminder_sent': True,
                'reminder_date': fields.Date.today(),
            })

        # On affiche une jolie notification de succès à l'écran
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Succès',
                'message': 'Le rappel a été généré et enregistré !',
                'sticky': False,
                'type': 'success',
            }
        }