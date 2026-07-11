from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

MSG_CAISSE_LECTURE_SEULE = _("Accès refusé: Vous avez uniquement un accès en lecture sur les caisses.")


class CashboxTransfer(models.Model):
    _name = "cashbox.transfer"
    _description = "Transfert de fonds entre caisses"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = " create_date desc, id desc"

    name = fields.Char(string='Référence', required=True, readonly=True, index=True, copy=False,
                       default='/')

    date = fields.Datetime(string='Date', required=True, default=fields.Datetime.now, tracking=True)
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string="Devise de la société",
    )
    amount = fields.Monetary(string='Montant', required=True, currency_field="company_currency_id", tracking=True)
    description = fields.Text(string='Description', required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('confirmed', 'Confirmé'),
        ('cancel', 'Annulé'),
    ], string='État', default='draft')

    user_id = fields.Many2one('res.users', 'Comptable', default=lambda self: self.env.user, readonly=True)
    notes = fields.Text(string='Notes Internes', tracking=True)
    company_id = fields.Many2one('res.company', string="Société", default=lambda self: self.env.company,
                                 required=True, index=True, tracking=True)

    source_cashbox_id = fields.Many2one('cashbox', string='Caisse Source',
                                        store=True,
                                        tracking=True,
                                        required=True,
                                        readonly=False,
                                        domain="[('responsible_ids', 'in', user_id)]",
                                        help="Caisse de la société depuis laquelle cette entrée a été effectuée.")
    destination_cashbox_id = fields.Many2one('cashbox', string='Caisse de Destination',
                                             tracking=True,
                                             required=True,
                                             help="Caisse de la société vers laquelle cette entrée a été transférée.")

    total_amount_destination_cashbox = fields.Monetary(related="destination_cashbox_id.total_amount",
                                                       string='Montant', currency_field="company_currency_id",
                                                       store=True)
    total_amount_source_cashbox = fields.Monetary(related="source_cashbox_id.total_amount",
                                                  currency_field="company_currency_id",
                                                  string='Montant', store=True)
    payment_id = fields.Many2one('account.payment', string='Paiement', readonly=True)

    def action_confirm(self):
        """Confirm the transfer, update cashbox balances, and change state to 'confirmed'."""
        for record in self:
            record.source_cashbox_id.total_amount -= record.amount  # Deduct from source
            record.destination_cashbox_id.total_amount += record.amount  # Add to destination
            record.state = 'confirmed'

    def action_cancel(self):
        """Cancel the transfer and revert the cashbox balances."""
        for record in self:
            record._revert_cashbox_balances()
            record.state = 'cancel'

    def action_to_draft(self):
        """Revert the transfer to draft state."""
        for record in self:
            paired_internal_transfer_payment_id = record.payment_id.paired_internal_transfer_payment_id
            if record.payment_id:
                record._revert_cashbox_balances()
                print('in', record.payment_id)
                paired_internal_transfer_payment_id.action_draft()
                paired_internal_transfer_payment_id.unlink()
                record.payment_id.action_draft()
                record.payment_id.unlink()
                record.state = 'draft'

    @api.model
    def create(self, vals):
        """Override create method to set a unique sequence for the transfer."""
        if self.env.user.has_group('caisse2.group_lecture_seule'):
            raise UserError(MSG_CAISSE_LECTURE_SEULE)
        if vals.get('name', '/') in (False, '/', ''):
            vals['name'] = self.env['ir.sequence'].next_by_code('cashbox.transfer') or '/'
        return super(CashboxTransfer, self).create(vals)

    def write(self, vals):
        if self.env.user.has_group('caisse2.group_lecture_seule'):
            raise UserError(MSG_CAISSE_LECTURE_SEULE)
        return super().write(vals)

    def _revert_cashbox_balances(self):
        """Revert the cashbox balances in case of transfer cancellation."""
        for rec in self:
            rec.source_cashbox_id.total_amount += rec.amount  # Add back to source
            rec.destination_cashbox_id.total_amount -= rec.amount  # Deduct from destination

    @api.onchange('source_cashbox_id', 'destination_cashbox_id', 'amount')
    def update_description(self):
        """Update the description based on the selected cashboxes."""
        if self.source_cashbox_id and self.destination_cashbox_id and (
                self.source_cashbox_id == self.destination_cashbox_id):
            raise UserError(_("La caisse de destination ne peut pas être la même que la caisse source."))

        if self.source_cashbox_id and self.destination_cashbox_id:
            self.description = f"Transfert De {self.amount} DA de la caisse {self.source_cashbox_id.name} vers la caisse {self.destination_cashbox_id.name}"
        else:
            self.description = ""

    @api.constrains('amount')
    def _check_amount(self):
        for record in self:
            if record.amount == 0.0:
                raise ValidationError("Le montant ne peut pas être égal à zéro.")

            if record.amount > record.source_cashbox_id.total_amount:
                raise ValidationError(
                    f"Le montant de la {record.source_cashbox_id.name} est insuffisant pour le transfert demandé."
                    f"\nMontant disponible : {record.source_cashbox_id.total_amount} DA.")

    def unlink(self):
        if self.env.user.has_group('caisse2.group_lecture_seule'):
            raise UserError(MSG_CAISSE_LECTURE_SEULE)
        for record in self:
            if record.state != 'draft':
                raise UserError(
                    _("Vous ne pouvez pas supprimer un transfert déjà confirmé.\nRemettez le transfert en brouillon avant de le supprimer"))
        return super(CashboxTransfer, self).unlink()

    def action_preview_report(self):
        """Prévisualiser le rapport dans un nouvel onglet"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/caisse2.report_cashbox_transfer_template/%s' % self.id,
            'target': 'new',
        }
