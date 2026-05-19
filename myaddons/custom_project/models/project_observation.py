# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class CustomProjectObservation(models.Model):
    _name = "custom.project.observation"
    _description = "Project Observation"
    _order = "create_date desc"
    _inherit = ['mail.thread', 'mail.activity.mixin']



    name = fields.Char(
        string='Reference',
        default=lambda self: _('New'),
        copy=False,
        readonly=True,
        tracking=True
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
        ],
        string='Status',
        default='draft',
        tracking=True
    )

    # =========================
    # ACTIONS
    # =========================
    def action_confirm(self):
        for rec in self:
            if not rec.observation_line_ids:
                raise UserError(_("You cannot confirm without observation lines."))
            rec.state = 'confirmed'

    def action_reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'
    project_id = fields.Many2one(
        'custom.project',
        string='Project',
        required=True,
        ondelete='cascade',
        tracking=True,
    )

    description = fields.Html(string='Observation', tracking=True)

    assigned_to_id = fields.Many2one(
        'res.users',
        string='Assigned To',
        tracking=True,
        domain="[('share', '=', False)]"
    )

    created_by_id = fields.Many2one(
        'res.users',
        string='Created By',
        default=lambda self: self.env.user,
        readonly=True
    )

    date_observation = fields.Datetime(
        string='Observation Date',
        default=lambda self: fields.Datetime.now(),
        tracking=True
    )

    observation_line_ids = fields.One2many(
        'custom.project.observation.line',
        'observation_id',
        string="Observation Stock"
    )

    # Button to create real consumption records from the observation lines
    def action_create_consumptions(self):
        """
        For each line with quantity_observation > 0, create a cunsomation.stock record.
        The consumption model's create() will check stock and deduct.
        """
        for obs in self:
            created = self.env['cunsomation.stock']
            errors = []
            for line in obs.observation_line_ids:
                qty = line.quantity_observation or 0.0
                if qty <= 0:
                    continue
                vals = {
                    'product_id': line.product_id.id,
                    'project_id': obs.project_id.id,
                    'quantity': qty,
                    'date_consumption': fields.Datetime.now(),
                    'company_id': obs.company_id.id if hasattr(obs, 'company_id') else obs.env.company.id,
                    'user_id': obs.env.user.id,
                }
                try:
                    created_rec = self.env['cunsomation.stock'].create(vals)
                    created |= created_rec
                except UserError as ue:
                    # collect error but continue other lines
                    errors.append(str(ue))
                except Exception as e:
                    errors.append(str(e))

            if errors:
                # show all errors to the user
                raise UserError(_("Some lines couldn't be converted:\n%s") % ("\n".join(errors)))

            if created:
                # optional: post a chatter message
                obs.message_post(body=_("Created %d consumption(s) from observation") % len(created))
        return True


class CustomProjectObservationLine(models.Model):
    _name = "custom.project.observation.line"
    _description = "Observation Line"

    observation_id = fields.Many2one(
        'custom.project.observation',
        string='Observation',
        ondelete='cascade',
        required=True
    )

    product_id = fields.Many2one(
        'product.product',
        string='Produit',
        required=True
    )

    quantity_observation = fields.Float(
        string='Quantité Prevision',
        default=0.0
    )

    quantity_stock = fields.Float(
        string='Quantité en stock',
        compute='_compute_quantities',
        store=False,
        readonly=True
    )

    quantity_consumed = fields.Float(
        string='Quantité consommée',
        compute='_compute_quantities',
        store=False,
        readonly=True
    )

    quantity_remaining = fields.Float(
        string='Reste en stock',
        compute='_compute_quantities',
        store=False,
        readonly=True
    )

    @api.depends('product_id', 'observation_id.project_id')
    def _compute_quantities(self):
        for line in self:
            stock_qty = 0.0
            consumed_qty = 0.0
            remaining = 0.0
            if line.product_id and line.observation_id and line.observation_id.project_id:
                project = line.observation_id.project_id

                stock = self.env['custom.stock'].search([
                    ('product_id', '=', line.product_id.id),
                    ('project_id', '=', project.id)
                ], limit=1)

                stock_qty = stock.quantity if stock else 0.0

                consumptions = self.env['cunsomation.stock'].search([
                    ('product_id', '=', line.product_id.id),
                    ('project_id', '=', project.id)
                ])
                consumed_qty = sum(consumptions.mapped('quantity')) if consumptions else 0.0

                remaining = stock_qty - consumed_qty

            line.quantity_stock = stock_qty
            line.quantity_consumed = consumed_qty
            line.quantity_remaining = remaining
    def write(self, vals):
        for rec in self:
            if rec.state == 'confirmed':
                forbidden_fields = set(vals.keys()) - {'state'}
                if forbidden_fields:
                    raise UserError(_("You cannot modify a confirmed observation."))
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError(_("You cannot delete a confirmed observation."))
        return super().unlink()

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """
        When selecting the product in a new line:
        - restrict domain to products present in project's stock
        - fill quantities (stock, consumed, remaining)
        """
        for rec in self:
            domain = [('id', '!=', False)]
            project = rec.observation_id.project_id if rec.observation_id else False
            if project:
                stocks = self.env['custom.stock'].search([('project_id', '=', project.id)])
                prods = stocks.mapped('product_id').ids
                if prods:
                    domain = [('id', 'in', prods)]
                else:
                    domain = [('id', '=', False)]

            # compute quantities (call compute explicitly for onchange)
            rec._compute_quantities()
            return {'domain': {'product_id': domain}}

    def write(self, vals):
        for rec in self:
            if rec.observation_id.state == 'confirmed':
                raise UserError(_("You cannot modify lines of a confirmed observation."))
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.observation_id.state == 'confirmed':
                raise UserError(_("You cannot delete lines of a confirmed observation."))
        return super().unlink()

