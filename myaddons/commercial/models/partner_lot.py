from odoo import models, fields, api


class CommercialPartnerLot(models.Model):
    _name = 'commercial.partner.lot'
    _description = 'Relation Contact - Lot'
    _rec_name = 'lot_id'

    partner_id = fields.Many2one('res.partner', string="Contact", required=True, ondelete='cascade')
    lot_id = fields.Many2one('commercial.lot', string="Lot", required=True, ondelete='cascade')
    remise = fields.Float(string="Remise", default=0.0)

    # Related fields for display
    numero_lot = fields.Char(related='lot_id.numero_lot', string="N° Lot", readonly=True)
    projet_id = fields.Many2one(related='lot_id.projet_id', string="Projet", readonly=True)
    bloc_id = fields.Many2one(related='lot_id.bloc_id', string="Bloc", readonly=True)
    etage_id = fields.Many2one(related='lot_id.etage_id', string="Étage", readonly=True)
    surface_globale = fields.Float(related='lot_id.surface_globale', string="Surface (m²)", readonly=True)
    montant_global = fields.Float(related='lot_id.montant_global', string="Montant", readonly=True)
    categorie_id = fields.Many2one(related='lot_id.categorie_id', string="Catégorie", readonly=True)
    state = fields.Selection(related='lot_id.state', string="État", readonly=True)
    source = fields.Selection(related='lot_id.source', string="Source", readonly=False)
    type_client_commercial = fields.Selection(
        related='partner_id.type_client_commercial', string="Type client", readonly=True)

    _sql_constraints = [
        ('unique_partner_lot', 'UNIQUE(partner_id, lot_id)',
         'Ce lot est déjà associé à ce contact.'),
    ]

    @api.onchange('lot_id')
    def _onchange_lot_id(self):
        if self.lot_id and self.lot_id.state in ('vendu', 'reserve'):
            lot = self.lot_id
            state_label = dict(lot._fields['state'].selection).get(lot.state)
            self.lot_id = False
            return {
                'warning': {
                    'title': "Sélection interdite",
                    'message': "Le lot %s est %s. Seuls les lots disponibles ou pré-réservés peuvent être sélectionnés." % (
                        lot.numero_lot, state_label),
                }
            }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('skip_lot_sync'):
            for rec in records:
                if rec.lot_id.id not in rec.partner_id.commercial_lot_ids.ids:
                    rec.partner_id.with_context(skip_lot_sync=True).write(
                        {'commercial_lot_ids': [(4, rec.lot_id.id)]})
        return records

    def unlink(self):
        if not self.env.context.get('skip_lot_sync'):
            for rec in self:
                rec.partner_id.with_context(skip_lot_sync=True).write(
                    {'commercial_lot_ids': [(3, rec.lot_id.id)]})
        return super().unlink()

    def action_view_versements(self):
        self.ensure_one()
        return self.lot_id.with_context(active_partner_id=self.partner_id.id).action_view_versements()

    def action_view_paiements(self):
        self.ensure_one()
        return self.lot_id.with_context(active_partner_id=self.partner_id.id).action_view_paiements()
