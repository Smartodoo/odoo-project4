from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    hotel_service = fields.Boolean(
        string="Consommation / service Auberge",
        help="Proposé à la réception pour être ajouté au séjour d'un client "
             "(petit-déjeuner, repas, boissons, blanchisserie…).")


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _hotel_night_product(self):
        """Produit « Nuitée » utilisé pour facturer l'hébergement (ses taxes et
        son compte de produits s'appliquent aux lignes chambre)."""
        return self.env.ref('hotel_management.product_hotel_night',
                            raise_if_not_found=False) or self.browse()

    @api.model
    def _hotel_check_stock_alerts(self):
        """Alerte stock minimum (cahier des charges §18) : les articles dont le
        stock prévu passe sous le seuil d'une règle de réapprovisionnement sont
        signalés aux responsables de l'auberge."""
        if 'stock.warehouse.orderpoint' not in self.env:
            return
        Orderpoint = self.env['stock.warehouse.orderpoint'].sudo()
        low = Orderpoint.search([('trigger', 'in', ('auto', 'manual'))]).filtered(
            lambda op: op.qty_forecast < op.product_min_qty)
        if not low:
            return
        group = self.env.ref('hotel_management.group_hotel_manager',
                             raise_if_not_found=False)
        user = (group.sudo().all_user_ids.filtered('active')[:1] if group
                else self.env['res.users']) or self.env.ref('base.user_admin')
        summary = _("Stock minimum atteint")
        for op in low:
            product = op.product_id.product_tmpl_id
            if product.activity_ids.filtered(lambda a: a.summary == summary):
                continue
            product.activity_schedule(
                'mail.mail_activity_data_todo', summary=summary,
                note=_("Stock prévu %(qty)s, minimum %(min)s : à commander.",
                       qty=op.qty_forecast, min=op.product_min_qty),
                user_id=user.id)


class HotelReservationService(models.Model):
    """Consommations et services ajoutés au séjour (cahier des charges §4 :
    check-out « ajout des consommations, ajout des services »)."""
    _name = 'hotel.reservation.service'
    _description = "Consommation / service d'un séjour"
    _order = 'date, id'

    reservation_id = fields.Many2one(
        'hotel.reservation', string="Réservation", required=True,
        ondelete='cascade', index=True)
    product_id = fields.Many2one(
        'product.product', string="Article", required=True,
        domain="[('hotel_service', '=', True)]")
    name = fields.Char(string="Désignation", required=True)
    date = fields.Date(string="Date", default=fields.Date.context_today, required=True)
    quantity = fields.Float(string="Quantité", default=1.0, digits='Product Unit')
    price_unit = fields.Monetary(string="Prix unitaire", currency_field='currency_id')
    price_subtotal = fields.Monetary(
        string="Montant", compute='_compute_subtotal', store=True,
        currency_field='currency_id')
    currency_id = fields.Many2one(related='reservation_id.currency_id', store=True)
    company_id = fields.Many2one(related='reservation_id.company_id', store=True)
    partner_id = fields.Many2one(related='reservation_id.partner_id', store=True)
    state = fields.Selection(related='reservation_id.state', store=True)

    @api.depends('quantity', 'price_unit')
    def _compute_subtotal(self):
        for rec in self:
            rec.price_subtotal = rec.quantity * rec.price_unit

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.display_name
            self.price_unit = self.product_id.lst_price

    @api.constrains('quantity', 'price_unit')
    def _check_values(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("La quantité d'une consommation doit être positive."))
            if rec.price_unit < 0:
                raise ValidationError(_("Le prix d'une consommation ne peut pas être négatif."))

    def _check_reservation_editable(self):
        for rec in self:
            resa = rec.reservation_id
            if resa.state == 'cancel':
                raise UserError(_("La réservation %s est annulée.", resa.name))
            if resa.invoice_ids.filtered(lambda m: m.state == 'posted'):
                raise UserError(_(
                    "La réservation %s est déjà facturée : ajoutez la consommation "
                    "sur une nouvelle facture ou annulez d'abord la facture.",
                    resa.name))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_reservation_editable()
        return records

    def write(self, vals):
        self._check_reservation_editable()
        return super().write(vals)

    def unlink(self):
        self._check_reservation_editable()
        return super().unlink()
