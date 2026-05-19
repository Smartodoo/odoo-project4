from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    prix_de_gros = fields.Float(
        'Prix de gros', default=1.0,
        digits='Product Price',
        help="Prix de gros",
    )
    margin_percentage = fields.Float(
        string="Marge (%)", compute="_compute_margin_percentage", store=True
    )

    @api.depends('list_price', 'standard_price')
    def _compute_margin_percentage(self):
        for product in self:
            if product.list_price > 0:
                product.margin_percentage = ((
                                                     product.list_price - product.standard_price) / product.standard_price) if product.standard_price > 0 else 0
                print('product.margin_percentage', product.margin_percentage)
            else:
                product.margin_percentage = 0
    def _get_buy_route(self):
        # Vérifie si les routes existent dans la base de données
        route_ids = [46, 50, 51, 16, 17, 12]
        existing_routes = self.env['stock.route'].browse(route_ids).filtered(lambda r: r.exists())
        print('existing_routes', existing_routes)
        return existing_routes.ids  # Retourne uniquement les routes valides

    def set_default_buy_route(self):
        for product in self:
            valid_routes = self._get_buy_route()
            print('valid_routes', valid_routes)
            if valid_routes:  # Appliquer uniquement si des routes valides existent
                product.write({'route_ids': [(6, 0, valid_routes)]})

    @api.model
    def create(self, vals):
        product = super(ProductTemplate, self).create(vals)
        product.detailed_type = 'product'
        product.set_default_buy_route()
        for route in product.route_ids:
            print(f"Route ID: {route.id}, Route Name: {route.name}")

        return product
