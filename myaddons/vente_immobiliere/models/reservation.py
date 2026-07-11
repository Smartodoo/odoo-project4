# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class VenteReservation(models.Model):
    _name = 'vente.reservation'
    _description = 'Réservation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Référence', readonly=True, copy=False, default='/')
    partner_id = fields.Many2one('res.partner', string='Client', required=True, tracking=True)
    appartement_id = fields.Many2one('vente.appartement', string='Appartement', required=True,
                                     tracking=True)
    projet_id = fields.Many2one(related='appartement_id.projet_id', string='Projet',
                                store=True, readonly=True)
    type = fields.Selection(related='projet_id.type', string='Type', store=True, readonly=True)
    date_reservation = fields.Date(string='Date de Réservation', default=fields.Date.today,
                                   tracking=True)
    date_confirmation = fields.Date(string='Date de Confirmation')
    date_vente = fields.Date(string='Date de Vente')
    price = fields.Monetary(string='Prix Convenu', currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Devise',
                                  related='projet_id.currency_id', store=True)
    note = fields.Text(string='Notes')
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('reserve', 'Réservé'),
        ('confirmed', 'Confirmé'),
        ('sold', 'Vendu'),
        ('cancelled', 'Annulé'),
    ], string='État', default='draft', tracking=True)
    sale_order_id = fields.Many2one('sale.order', string='Bon de Commande', readonly=True,
                                    copy=False)
    company_id = fields.Many2one('res.company', string='Société',
                                 default=lambda self: self.env.company, required=True)
    user_id = fields.Many2one('res.users', string='Commercial',
                              default=lambda self: self.env.user, tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') in (False, '/', ''):
                vals['name'] = self.env['ir.sequence'].next_by_code('vente.reservation') or '/'
        return super().create(vals_list)

    def action_reserve(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Seules les réservations en brouillon peuvent être réservées."))
            if rec.appartement_id.state != 'disponible':
                raise UserError(_("L'appartement '%s' n'est pas disponible.") % rec.appartement_id.name)
            rec.appartement_id.state = 'reserve'
            rec.state = 'reserve'

    def action_confirm(self):
        for rec in self:
            if rec.state != 'reserve':
                raise UserError(_("Seules les réservations réservées peuvent être confirmées."))
            rec.date_confirmation = fields.Date.today()
            rec.state = 'confirmed'

    def action_sell(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(_("Seules les réservations confirmées peuvent être vendues."))
            rec.date_vente = fields.Date.today()
            rec.appartement_id.state = 'vendu'
            rec.state = 'sold'
            rec._create_sale_order()

    def action_cancel(self):
        for rec in self:
            if rec.state == 'cancelled':
                raise UserError(_("Cette réservation est déjà annulée."))
            if rec.state in ('reserve', 'confirmed'):
                rec.appartement_id.state = 'disponible'
            rec.state = 'cancelled'

    def _create_sale_order(self):
        self.ensure_one()
        sale_order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'origin': self.name,
            'order_line': [(0, 0, {
                'name': _("Appartement %s - %s") % (self.appartement_id.name, self.projet_id.name),
                'product_uom_qty': 1,
                'price_unit': self.price,
            })],
        })
        self.sale_order_id = sale_order.id
        sale_order.action_confirm()

    def action_view_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_("Aucun bon de commande lié à cette réservation."))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bon de Commande',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }
