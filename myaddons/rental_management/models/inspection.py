# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class PropertyInspection(models.Model):
    _name = 'property.inspection'
    _description = 'État des Lieux'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc'

    name = fields.Char("N° Inspection", readonly=True, default="/", copy=False)

    rental_id = fields.Many2one('property.rental', string="Location", required=True)
    apartment_id = fields.Many2one('property.apartment', string="Appartement",
                                   related='rental_id.property_id', store=True)

    inspection_type = fields.Selection([
        ('entry', ' Entrée'),
        ('exit', ' Sortie'),
        ('routine', ' Routine'),
        ('damage', ' Dégâts'),
    ], string="Type", required=True, default='entry')

    date = fields.Date("Date", default=fields.Date.context_today, required=True)
    inspector_id = fields.Many2one('res.users', string="Inspecteur",
                                   default=lambda self: self.env.user)

    # ============================================
    # CHECKLIST ÉTAT
    # ============================================
    # Murs & Plafond
    walls_condition = fields.Selection([
        ('excellent', '⭐ Excellent'),
        ('good', ' Bon'),
        ('fair', ' Passable'),
        ('bad', 'Mauvais'),
    ], string="Murs & Plafond", default='good')

    floor_condition = fields.Selection([
        ('excellent', '⭐ Excellent'),
        ('good', 'Bon'),
        ('fair', ' Passable'),
        ('bad', ' Mauvais'),
    ], string="Sol", default='good')

    # Équipements
    plumbing_working = fields.Boolean("Plomberie OK", default=True)
    electricity_working = fields.Boolean(" Électricité OK", default=True)
    ac_working = fields.Boolean(" Clim OK", default=True)
    wifi_working = fields.Boolean(" WiFi OK", default=True)
    tv_working = fields.Boolean(" TV OK", default=True)
    kitchen_working = fields.Boolean("Cuisine OK", default=True)

    # Propreté
    cleanliness = fields.Selection([
        ('excellent', '⭐ Excellent'),
        ('good', ' Bon'),
        ('fair', '️ Passable'),
        ('bad', ' Mauvais'),
    ], string="Propreté", default='good')

    # ============================================
    # PHOTOS & DOCUMENTS
    # ============================================
    photos_before = fields.Many2many('ir.attachment', 'inspection_photos_before_rel',
                                     string="Photos Avant")
    photos_after = fields.Many2many('ir.attachment', 'inspection_photos_after_rel',
                                    string="Photos Après")

    # ============================================
    # SIGNATURES
    # ============================================
    tenant_signature = fields.Binary("✍️ Signature Locataire")
    inspector_signature = fields.Binary("✍️ Signature Inspecteur")

    # ============================================
    # DÉGÂTS & COÛTS
    # ============================================
    damage_found = fields.Boolean("Dégâts Constastés", default=False)
    damage_description = fields.Text("Description des Dégâts")
    damage_photos = fields.Many2many('ir.attachment', 'inspection_damage_photos_rel',
                                     string="Photos Dégâts")

    estimated_repair_cost = fields.Float("Coût Réparations Estimé")
    actual_repair_cost = fields.Float("Coût Réparations Réel")

    # Retenue sur caution
    deposit_deduction = fields.Float("Retenue Caution")

    # ============================================
    # NOTES
    # ============================================
    notes = fields.Text("Observations Générales")

    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('done', ' Terminé'),
        ('disputed', '️ Contesté'),
    ], string="État", default='draft')

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('property.inspection') or 'INS/NEW'
        return super(PropertyInspection, self).create(vals)

    def action_done(self):
        self.write({'state': 'done'})
        # Mettre à jour la location si c'est une sortie
        for rec in self:
            if rec.inspection_type == 'exit':
                rec.rental_id.write({'state': 'done'})
                rec.apartment_id.write({'state': 'available'})
                rec.message_post(body=_("✅ État des lieux de sortie validé. Appartement libéré."))

    def action_dispute(self):
        self.write({'state': 'disputed'})
        # Créer activité pour le gérant
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary="État des lieux contesté - %s" % self.name,
            user_id=self.env.user.id,
            note=self.damage_description or "Le locataire conteste l'état des lieux."
        )