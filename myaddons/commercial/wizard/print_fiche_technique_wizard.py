from odoo import models, fields, api


class PrintClientWizard(models.TransientModel):
    _name = 'commercial.print.client.wizard'
    _description = "Wizard impression client"

    partner_id = fields.Many2one('res.partner', string="Client", required=True)
    type_impression = fields.Selection([
        ('fiche_technique', 'Fiche Technique'),
        ('attestation_affectation', "Attestation d'affectation"),
        ('attestation_reservation_cb', "Attestation de réservation par CB"),
        ('attestation_provisoire', "Attestation d'affectation provisoire"),
        ('fiche_client', "Fiche Client"),
    ], string="Type d'impression", required=True)
    lot_id = fields.Many2one(
        'commercial.lot', string="Lot",
        domain="[('id', 'in', available_lot_ids)]")
    type_facade = fields.Selection([
        ('interieure', 'Façade principale'),
        ('posterieure', 'Façade postérieure'),
    ], string="Type de façade")
    avec_montants = fields.Boolean(string="Avec les montants", default=False)
    available_lot_ids = fields.Many2many(
        'commercial.lot', compute='_compute_available_lot_ids')

    @api.depends('partner_id')
    def _compute_available_lot_ids(self):
        for rec in self:
            rec.available_lot_ids = rec.partner_id.commercial_lot_ids

    def action_print(self):
        self.ensure_one()
        if self.type_impression == 'fiche_technique' and self.lot_id:
            return self.env.ref(
                'commercial.action_report_fiche_technique'
            ).report_action(self)
        if self.type_impression == 'attestation_affectation' and self.lot_id:
            return self.env.ref(
                'commercial.action_report_attestation_affectation'
            ).report_action(self)
        if self.type_impression == 'attestation_reservation_cb' and self.lot_id:
            return self.env.ref(
                'commercial.action_report_attestation_reservation_cb'
            ).report_action(self)
        if self.type_impression == 'attestation_provisoire' and self.lot_id:
            return self.env.ref(
                'commercial.action_report_attestation_provisoire'
            ).report_action(self)
        if self.type_impression == 'fiche_client':
            return self.env.ref(
                'commercial.action_report_fiche_client'
            ).report_action(self)
