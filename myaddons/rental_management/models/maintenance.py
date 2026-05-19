# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class PropertyMaintenance(models.Model):
    _name = 'property.maintenance'
    _description = 'Ticket de Maintenance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, date_reported desc'

    name = fields.Char("N° Ticket", readonly=True, default="/", copy=False)

    apartment_id = fields.Many2one('property.apartment', string="Appartement", required=True)

    # ============================================
    # SIGNALEMENT
    # ============================================
    reported_by = fields.Many2one('res.partner', string="Signalé par")
    reported_by_type = fields.Selection([
        ('tenant', 'Locataire'),
        ('staff', 'Personnel'),
        ('system', 'Système'),
    ], string="Source", default='tenant')

    date_reported = fields.Date("Date Signalement", default=fields.Date.context_today)
    date_scheduled = fields.Date("Date Prévue Intervention")
    date_completed = fields.Date("Date Terminé")

    # ============================================
    # CATÉGORIE & PRIORITÉ
    # ============================================
    category = fields.Selection([
        ('plumbing', '🚰 Plomberie'),
        ('electricity', '💡 Électricité'),
        ('ac', '❄️ Climatisation'),
        ('wifi', '📶 Internet'),
        ('appliance', '🔌 Électroménager'),
        ('security', '🔒 Sécurité'),
        ('cleaning', '🧹 Propreté'),
        ('other', '📦 Autre'),
    ], string="Catégorie", required=True)

    priority = fields.Selection([
        ('0', '🟢 Faible'),
        ('1', '🟡 Normale'),
        ('2', '🟠 Haute'),
        ('3', '🔴 Urgente'),
    ], string="Priorité", default='1')

    # ============================================
    # DESCRIPTION
    # ============================================
    description = fields.Text("Description du Problème", required=True)
    photos = fields.Many2many('ir.attachment', string="Photos")

    # ============================================
    # INTERVENTION
    # ============================================
    assigned_to = fields.Many2one('res.users', string="Assigné à")
    provider_id = fields.Many2one('res.partner', string="Prestataire Externe")

    estimated_cost = fields.Float("Coût Estimé")
    actual_cost = fields.Float("Coût Réel")

    # ============================================
    # RÉSOLUTION
    # ============================================
    resolution = fields.Text("Description Résolution")
    parts_used = fields.Text("Pièces Remplacées")

    # ============================================
    # STATUT
    # ============================================
    state = fields.Selection([
        ('new', '🆕 Nouveau'),
        ('confirmed', '✅ Confirmé'),
        ('in_progress', '🔧 En Cours'),
        ('done', '✅ Terminé'),
        ('cancelled', '❌ Annulé'),
    ], string="État", default='new', tracking=True)

    # Satisfaction
    tenant_satisfaction = fields.Selection([
        ('5', '⭐⭐⭐⭐⭐ Excellent'),
        ('4', '⭐⭐⭐⭐ Bon'),
        ('3', '⭐⭐⭐ Moyen'),
        ('2', '⭐⭐ Mauvais'),
        ('1', '⭐ Très Mauvais'),
    ], string="Satisfaction Locataire")

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('property.maintenance') or 'MAINT/NEW'
        return super(PropertyMaintenance, self).create(vals)

    def action_confirm(self):
        self.write({'state': 'confirmed'})
        # Créer activité pour le technicien
        if self.assigned_to:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary="Nouvelle maintenance: %s" % self.name,
                user_id=self.assigned_to.id,
                note=self.description
            )

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_wait_parts(self):
        self.write({'state': 'waiting_parts'})

    def action_done(self):
        self.write({
            'state': 'done',
            'date_completed': fields.Date.today(),
        })
        # Notifier le locataire
        if self.reported_by and self.reported_by_type == 'tenant':
            template = self.env.ref('rental_management.email_maintenance_done')
            template.send_mail(self.id, force_send=True)

    def action_cancel(self):
        self.write({'state': 'cancelled'})