# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta

class PropertyRental(models.Model):
    _name = 'property.rental'
    _description = 'Contrat de Location'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc'

    # ============================================
    # IDENTIFICATION
    # ============================================
    name = fields.Char("N° Contrat", readonly=True, default="/", copy=False)

    # ============================================
    # RELATIONS
    # ============================================
    property_id = fields.Many2one(
        'property.apartment',
        string="Appartement",
        required=True,
        tracking=True,
        domain="[('state', 'in', ['available', 'soon'])]"
    )

    client_id = fields.Many2one(
        'res.partner',
        string="Locataire",
        required=True,
        tracking=True
    )

    # ============================================
    # DATES
    # ============================================
    date_start = fields.Date("Date d'Arrivée", default=fields.Date.context_today, required=True)
    date_end = fields.Date("Date de Départ", required=True)

    # ============================================
    # CALCULS AUTO (PRIX & DURÉE)
    # ============================================
    duration_days = fields.Integer(
        string="Durée (Jours)",
        compute="_compute_pricing",
        store=True,
        readonly=True
    )

    period_type = fields.Selection([
        ('day', '📅 Journalier'),
        ('week', '📅 Hebdomadaire'),
        ('month', '📅 Mensuel'),
        ('year', '📅 Annuel'),
    ], string="Type de Période", compute="_compute_pricing", store=True, readonly=True)

    unit_price = fields.Float(
        string="Prix Unitaire (DA)",
        compute="_compute_pricing",
        store=True,
        readonly=False,
    )

    total_price = fields.Float(
        string="Total à Payer (DA)",
        compute="_compute_pricing",
        store=True,
        readonly=True
    )

    # ============================================
    # CAUTION
    # ============================================
    deposit_amount = fields.Float(
        string="Caution (DA)",
        compute="_compute_deposit",
        store=True,
        readonly=False
    )
    deposit_returned = fields.Boolean("Caution Restituée", default=False)
    deposit_return_date = fields.Date("Date Restitution")
    deposit_deduction = fields.Float("Retenue sur Caution")
    deposit_notes = fields.Text("Notes Caution")

    # ============================================
    # FINANCIER & PAIEMENTS
    # ============================================
    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        default=lambda self: self.env.company.currency_id,
        readonly=True
    )

    amount_paid = fields.Float("Montant Payé", default=0.0, tracking=True)

    amount_due = fields.Float(
        string="Reste à payer",
        compute="_compute_residual",
        store=True,
        readonly=True
    )

    payment_status = fields.Selection([
        ('unpaid', '❌ Non Payé'),
        ('partial', '⚠️ Partiel'),
        ('paid', '✅ Payé'),
    ], string="État Paiement", compute="_compute_payment_status", store=True)

    # ============================================
    # STATUT DU CONTRAT
    # ============================================
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('confirmed', '✅ Confirmé'),
        ('ongoing', '🟢 En Cours'),
        ('expiring', '🟠 Bientôt Terminé'),
        ('done', '🔒 Terminé'),
        ('cancelled', '❌ Annulé'),
    ], string="État", default='draft', tracking=True)

    days_remaining = fields.Integer("Jours Restants", compute="_compute_days_remaining")
    is_expiring_soon = fields.Boolean("Expire Bientôt", compute="_compute_days_remaining")

    # ============================================
    # RELATIONS INVERSES
    # ============================================
    inspection_ids = fields.One2many('property.inspection', 'rental_id', string="États des Lieux")
    payment_ids = fields.One2many('rental.payment', 'rental_id', string="Paiements")
    service_ids = fields.One2many('rental.service', 'rental_id', string="Prestations")
    notes = fields.Text("Notes / Commentaires")

    # ============================================
    # LOGIQUE DE CALCUL (COMPUTE & ONCHANGE)
    # ============================================

    @api.depends('total_price', 'amount_paid')
    def _compute_residual(self):
        for record in self:
            record.amount_due = max(record.total_price - record.amount_paid, 0)

    @api.depends('date_start', 'date_end', 'property_id', 'unit_price')
    def _compute_pricing(self):
        for rec in self:
            # 1. Calcul de la durée
            if rec.date_start and rec.date_end:
                delta = (rec.date_end - rec.date_start).days
                rec.duration_days = max(delta + 1, 0)
            else:
                rec.duration_days = 0

            # 2. Calcul du prix (Logique simplifiée sans get_best_price)
            if rec.property_id and rec.duration_days > 0:
                # On détermine le type de période par défaut
                if rec.duration_days >= 365:
                    rec.period_type = 'year'
                    price = rec.property_id.price_year
                elif rec.duration_days >= 30:
                    rec.period_type = 'month'
                    price = rec.property_id.price_month
                elif rec.duration_days >= 7:
                    rec.period_type = 'week'
                    price = rec.property_id.price_week
                else:
                    rec.period_type = 'day'
                    price = rec.property_id.price_day

                # On fixe le prix unitaire si l'utilisateur ne l'a pas fait
                if not rec.unit_price or rec.unit_price == 0.0:
                    rec.unit_price = price or rec.property_id.price_day

                # Calcul du total
                factors = {'year': 365.0, 'month': 30.0, 'week': 7.0, 'day': 1.0}
                factor = factors.get(rec.period_type, 1.0)

                if rec.period_type == 'day':
                    rec.total_price = rec.duration_days * rec.unit_price
                else:
                    rec.total_price = (rec.duration_days / factor) * rec.unit_price
            else:
                rec.total_price = 0.0
                rec.period_type = 'day'

    @api.onchange('property_id', 'date_start', 'date_end', 'unit_price')
    def _onchange_prices_refresh(self):
        self._compute_pricing()
        self._compute_deposit()

    @api.depends('amount_due', 'total_price', 'amount_paid')
    def _compute_payment_status(self):
        for rec in self:
            if rec.total_price <= 0:
                rec.payment_status = 'unpaid'
            elif rec.amount_paid >= rec.total_price:
                rec.payment_status = 'paid'
            elif rec.amount_paid > 0:
                rec.payment_status = 'partial'
            else:
                rec.payment_status = 'unpaid'

    @api.depends('property_id', 'duration_days', 'client_id', 'total_price')
    def _compute_deposit(self):
        for rec in self:
            if not rec.property_id:
                rec.deposit_amount = 0
                continue
            base = rec.property_id.price_day * 5 if rec.duration_days < 7 else rec.property_id.price_month * 2
            if rec.client_id and hasattr(rec.client_id, 'rental_count') and rec.client_id.rental_count > 3:
                base *= 0.5
            rec.deposit_amount = min(base, rec.total_price * 0.5)

    @api.depends('date_end', 'state')
    def _compute_days_remaining(self):
        today = fields.Date.today()
        for rec in self:
            if rec.date_end and rec.state in ('confirmed', 'ongoing', 'expiring'):
                rec.days_remaining = (rec.date_end - today).days
                rec.is_expiring_soon = 0 <= rec.days_remaining <= 7
            else:
                rec.days_remaining = 0
                rec.is_expiring_soon = False

    # ============================================
    # ACTIONS BOUTONS (ALIGNÉS À GAUCHE !)
    # ============================================
    def action_confirm(self):
        for rec in self:
            if rec.property_id.state not in ('available', 'soon'):
                raise ValidationError(_("Appartement non disponible."))
            rec.property_id.write({'state': 'occupied'})
            rec.write({'state': 'confirmed'})
        return True

    def action_start(self):
        self.write({'state': 'ongoing'})

    def action_set_expiring(self):
        for rec in self:
            rec.write({'state': 'expiring'})
            if rec.property_id:
                rec.property_id.write({'state': 'soon'})

    def action_done(self):
        for rec in self:
            rec.write({'state': 'done'})
            if rec.property_id:
                rec.property_id.write({'state': 'available'})

    def action_cancel(self):
        for rec in self:
            rec.write({'state': 'cancelled'})
            if rec.property_id:
                rec.property_id.write({'state': 'available'})

    def action_set_to_draft(self):
        self.write({'state': 'draft'})

    def action_generate_contract(self):
        # Appelle le rapport "Contrat de Location" que tu viens de créer
        return self.env.ref('rental_management.report_rental_contract').report_action(self)

    def action_generate_quittance(self):
        # Appelle le rapport "Quittance de Loyer"
        return self.env.ref('rental_management.report_quittance').report_action(self)


    def action_register_payment(self):
        """ Ouvre une fenêtre pour enregistrer un nouveau paiement """
        self.ensure_one()  # Sécurité pour s'assurer qu'on ne traite qu'un contrat à la fois

        return {
            'name': _('Enregistrer un Paiement'),
            'type': 'ir.actions.act_window',
            'res_model': 'rental.payment',  # Vérifie bien que c'est le nom de ton modèle de paiement
            'view_mode': 'form',
            'target': 'new',  # 'new' permet d'ouvrir en mode "pop-up" (wizard)
            'context': {
                'default_rental_id': self.id,
                'default_amount': self.amount_due,  # Pré-remplir avec ce qu'il reste à payer
                'default_partner_id': self.client_id.id,
            }
        }

    def action_view_payments(self):
        return {
            'name': _('Paiements'),
            'type': 'ir.actions.act_window',
            'res_model': 'rental.payment',
            'view_mode': 'tree,form',
            'domain': [('rental_id', '=', self.id)],
        }

    def action_create_service(self):
        """ Ouvre un formulaire pour ajouter une prestation à cette location """
        self.ensure_one()
        return {
            'name': _('Ajouter une Prestation'),
            'type': 'ir.actions.act_window',
            'res_model': 'rental.service',  # Nom du modèle qui gère les services
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_rental_id': self.id,
                'default_partner_id': self.client_id.id,
            }
        }

    # ============================================
    # CONTRAINTES & OVERRIDES
    # ============================================
    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_end and rec.date_start and rec.date_end <= rec.date_start:
                raise ValidationError(_("La date de départ doit être APRÈS la date d'arrivée !"))

    @api.constrains('property_id', 'date_start', 'date_end', 'state')
    def _check_availability(self):
        for rec in self:
            if rec.state in ('draft', 'cancelled', 'done'):
                continue
            domain = [
                ('property_id', '=', rec.property_id.id),
                ('id', '!=', rec.id),
                ('state', 'in', ('confirmed', 'ongoing', 'expiring')),
                ('date_start', '<', rec.date_end),
                ('date_end', '>', rec.date_start),
            ]
            if self.search_count(domain) > 0:
                raise ValidationError(_("Cet appartement est déjà réservé !"))

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('property.rental') or 'LOC/NEW'
        return super(PropertyRental, self).create(vals)