from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date, datetime

MSG_CAISSE_LECTURE_SEULE = _("Accès refusé: Vous avez uniquement un accès en lecture sur les caisses.")


class CaisseExpense(models.Model):
    _name = "caisse.expense"
    _description = "Décaissement situation de la société"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = " create_date desc, id desc"

    name = fields.Char(string='Réference', required=True, readonly=True, index=True, copy=False,
                       default='/')

    date = fields.Datetime(string='Date', required=True, default=fields.Datetime.now, tracking=True)
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string="Devise de la société",
    )
    company_id = fields.Many2one('res.company', string="Société", default=lambda self: self.env.company,
                                 required=True, index=True, tracking=True)
    description = fields.Text(string='Description', required=True, tracking=True)
    notes = fields.Text(string='Notes Internes', tracking=True)
    state = fields.Selection([
        ('draft', 'À soumettre'),
        ('approuve', 'Approuvé'),
    ], string='État', default='draft', tracking=True)

    amount = fields.Monetary(string='Montant', currency_field="company_currency_id", store=True, tracking=True)
    cashbox_id = fields.Many2one('cashbox', string='Caisse',
                                 store=True,
                                 tracking=True,
                                 required=True,
                                 readonly=False,
                                 help="Caisse de la société au sein de laquelle cette sortie a été effectuée.")
    user_id = fields.Many2one('res.users', 'Caissier', default=lambda self: self.env.user, readonly=True)
    employee_id = fields.Many2one('hr.employee', 'Employé', default=lambda self: self.env.user.employee_id)
    # payment_id = fields.Many2one('paiement.situation', string='Paiement', readonly=True)
    situation_id = fields.Many2one('situation', string='Situation', readonly=True)
    project_id = fields.Many2one('custom.project', string='Projet', related='situation_id.project_id', store=True, readonly=True)
    amount_paid = fields.Monetary(string='Versement',
                                  currency_field="company_currency_id", tracking=True, store=True)
    amount_residual = fields.Monetary(string='Reste à payer',
                                      store=True,
                                      currency_field="company_currency_id", tracking=True)

    # amount_verse = fields.Float(string='Versé', currency_field="company_currency_id", tracking=True, store=True)
    amount_verse = fields.Monetary(
        string='Versé',
        currency_field="company_currency_id",
        tracking=True,
        store=True
    )

    is_totally_paid = fields.Boolean(string="Totalement payé", compute='_compute_is_totally_paid', store=True)
    is_partially_paid = fields.Boolean(string="Partiellement payé", compute='_compute_is_partially_paid', store=True)

    @api.depends('amount', 'amount_verse')
    def _compute_is_totally_paid(self):
        for record in self:
            record.is_totally_paid = record.amount_residual == 0

    @api.depends('amount', 'amount_verse')
    def _compute_is_partially_paid(self):
        for record in self:
            record.is_partially_paid = 0 < record.amount_residual < record.amount

    @api.model
    def create(self, vals):
        if self.env.user.has_group('caisse2.group_lecture_seule'):
            raise UserError(MSG_CAISSE_LECTURE_SEULE)
        rec = super().create(vals)
        if vals.get('name', '/') in (False, '/', ''):
            vals['name'] = self.env['ir.sequence'].next_by_code('caisse.expense') or '/'
        # TO debit / credit the cashbox total amount
        if 'state' in vals and vals.get('state') == 'approuve':
            rec.cashbox_id.total_amount -= rec.amount_paid
        elif 'state' in vals and rec.state == 'approuve' and vals.get('state') == 'draft':
            rec.cashbox_id.total_amount += rec.amount_paid
        # a chaque creation de caisse.expense on cree un record dans caisse.expense.globale avec le nom du partenaire et on ajoute la ligne dans les lignes de depenses

        return rec

    def write(self, vals):
        if self.env.user.has_group('caisse2.group_lecture_seule'):
            raise UserError(MSG_CAISSE_LECTURE_SEULE)
        for record in self:
            if 'state' in vals:
                if record.state != vals.get('state'):
                    if vals.get('state') == 'approuve':
                        record.cashbox_id.total_amount -= record.amount_paid
                        caisse_expense_globale_obj = self.env['caisse.expense.globale']
                        partenaire = record.situation_id.original_subcontractor_id
                        caisse_expense_globale = caisse_expense_globale_obj.search(
                            [('partner_id', '=', partenaire.id)], limit=1)
                        if not caisse_expense_globale:
                            caisse_expense_globale = caisse_expense_globale_obj.create({
                                'partner_id': partenaire.id,
                                'date_from': datetime.now(),
                                'date_to': datetime.now(),
                                'company_id': record.company_id.id,
                                'user_id': record.env.user.id,
                                'partner_type': 'SUBCONTRACTOR',

                            })
                        caisse_expense_globale.write({
                            'expenses_line_ids': [(4, record.id)]
                        })

                        # Créer/Mettre à jour le récapitulatif par projet
                        if record.project_id:
                            record._update_project_recap()
                    elif vals.get('state') == 'draft' and record.state == 'approuve':
                        record.cashbox_id.total_amount += record.amount
        return super(CaisseExpense, self).write(vals)

    def _update_project_recap(self):
        """Crée ou met à jour le récapitulatif de dépenses par projet"""
        self.ensure_one()
        if not self.project_id:
            return

        caisse_expense_project_obj = self.env['caisse.expense.project']
        project_recap = caisse_expense_project_obj.search([
            ('project_id', '=', self.project_id.id)
        ], limit=1)

        if not project_recap:
            project_recap = caisse_expense_project_obj.create({
                'project_id': self.project_id.id,
                'date_from': datetime.now(),
                'date_to': datetime.now(),
                'company_id': self.company_id.id,
                'user_id': self.env.user.id,
            })

        project_recap.write({
            'expenses_line_ids': [(4, self.id)]
        })

    def unlink(self):
        if self.env.user.has_group('caisse2.group_lecture_seule'):
            raise UserError(MSG_CAISSE_LECTURE_SEULE)
        for record in self:
            if record.state != 'draft':
                raise UserError(_("Vous ne pouvez pas supprimer un paeiment approuvé."))
        return super(CaisseExpense, self).unlink()

    def action_preview_report(self):
        """Prévisualiser le rapport dans un nouvel onglet"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/caisse2.report_caisse_expense_situation/%s' % self.id,
            'target': 'new',
        }

    def action_preview_report_multi(self):
        """Prévisualiser le rapport pour plusieurs enregistrements sélectionnés"""
        if not self:
            raise UserError(_("Veuillez sélectionner au moins un enregistrement."))
        ids_str = ','.join(str(rec.id) for rec in self)
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/caisse2.report_caisse_expense_situation/%s' % ids_str,
            'target': 'new',
        }
