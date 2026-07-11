from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime

MSG_ACHAT_LECTURE_SEULE = _("Accès refusé: Vous avez uniquement un accès en lecture sur les achats.")


class PurchaseOrderInheri(models.Model):
    _inherit = 'purchase.order'

    active = fields.Boolean(default=True)  # Permet d'archiver les bons de commande
    payment_purchase_ids = fields.One2many('account.payment', 'purchase_order_id', string='Payments')
    amount_paid_purchase = fields.Monetary(string="Montant payé", compute="_compute_amount_paid", store=True)
    payment_count_purchase = fields.Integer(string="Nombre de paiements", compute="_compute_payment_count", store=True)
    amount_due_purchase = fields.Monetary(string="Montant dû", compute="_compute_amount_due", store=True)
    is_payment_term_purchase = fields.Boolean(string="À Terme", compute="_compute_is_payment_term", store=True)
    date_bon = fields.Datetime(string="date de bon", default=fields.Datetime.now)
    project_id = fields.Many2one(
        'custom.project',
        string="Projet",
        domain="[('company_id', '=', allowed_company_ids[0])]",
    )
    show_payment_button_purchase = fields.Boolean(compute="_compute_show_payment_button_purchase")
    num_bl = fields.Char(string="N° BL")
    num_facture = fields.Char(string="N° Facture")

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user.has_group('Purchase_custom.group_achat_lecture_seule'):
            raise UserError(MSG_ACHAT_LECTURE_SEULE)
        return super().create(vals_list)

    def write(self, vals):
        if self.env.user.has_group('Purchase_custom.group_achat_lecture_seule'):
            raise UserError(MSG_ACHAT_LECTURE_SEULE)
        return super().write(vals)

    def unlink(self):
        if self.env.user.has_group('Purchase_custom.group_achat_lecture_seule'):
            raise UserError(MSG_ACHAT_LECTURE_SEULE)
        return super().unlink()

    def _compute_show_payment_button_purchase(self):
        for rec in self:
            rec.show_payment_button_purchase = not self.env.user.has_group('custom_groups.group_technique')

    def action_cancel(self):
        """
        Annuler le bon de commande à tout moment, même si la réception est validée.
        Cette méthode permet au client de corriger les erreurs.
        Gère également l'annulation des paiements et des dépenses caisse associées.
        """
        for order in self:
            # 1. Gérer les dépenses caisse fournisseur liées
            expense_suppliers = self.env['caisse.expense.supplier'].sudo().search([
                ('purchase_id', '=', order.id)
            ])
            for expense in expense_suppliers:
                # Si approuvé, remettre en brouillon pour recréditer la caisse
                if expense.state == 'approuve':
                    expense.sudo().write({'state': 'draft'})

                # Retirer des récaps globales
                globale_records = self.env['caisse.expense.globale'].sudo().search([
                    ('expenses_supplier_line_ids', 'in', expense.id)
                ])
                for globale in globale_records:
                    globale.sudo().write({'expenses_supplier_line_ids': [(3, expense.id)]})

                # Retirer des récaps par projet
                project_records = self.env['caisse.expense.project'].sudo().search([
                    ('expenses_supplier_line_ids', 'in', expense.id)
                ])
                for project_rec in project_records:
                    project_rec.sudo().write({'expenses_supplier_line_ids': [(3, expense.id)]})

                # Supprimer la dépense
                expense.sudo().unlink()

            # 2. Annuler les paiements liés
            for payment in order.payment_purchase_ids:
                # Retirer le paiement des versements
                versements = self.env['versement.versement'].sudo().search([
                    ('paiement_ids', 'in', payment.id)
                ])
                for versement in versements:
                    versement.sudo().write({'paiement_ids': [(3, payment.id)]})
                    # Si le versement n'a plus de paiements, le remettre en brouillon
                    if not versement.paiement_ids:
                        if versement.state == 'payed':
                            versement.sudo().write({'state': 'done'})

                # Annuler le paiement
                if payment.state == 'posted':
                    payment.sudo().action_draft()
                if payment.state == 'draft':
                    payment.sudo().action_cancel()

            # 3. Annuler les réceptions (pickings) liées
            for picking in order.picking_ids:
                if picking.state == 'done':
                    # Créer un picking retour pour annuler la réception validée
                    stock_return_picking = self.env['stock.return.picking']
                    return_wizard = stock_return_picking.with_context(
                        active_id=picking.id,
                        active_ids=picking.ids,
                        active_model='stock.picking'
                    ).create({'picking_id': picking.id})
                    # Utiliser create_returns() pour Odoo 17
                    return_picking = return_wizard.create_returns()
                    return_picking_id = return_picking.get('res_id')
                    if return_picking_id:
                        return_pick = self.env['stock.picking'].browse(return_picking_id)
                        # Valider le retour automatiquement
                        if return_pick.state == 'draft':
                            return_pick.action_confirm()
                        if return_pick.state == 'confirmed':
                            return_pick.action_assign()
                        for move in return_pick.move_ids:
                            move.quantity = move.product_uom_qty
                        return_pick.button_validate()
                elif picking.state != 'cancel':
                    picking.action_cancel()

            # 4. Mettre le bon de commande en état annulé
            order.write({'state': 'cancel'})

        return True

    def action_preview_bon_commande(self):
        """Prévisualiser le Bon de Commande dans un nouvel onglet"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/Purchase_custom.report_bon_commande_document/%s' % self.id,
            'target': 'new',
        }

    def button_confirm(self):
        # 1) Appel du standard pour créer le picking normalement
        res = super().button_confirm()

        for order in self:
            # 🚚 2) Valider immédiatement les réceptions
            for picking in order.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')):
                # Confirmer le picking s'il est en 'draft'
                if picking.state == 'draft':
                    picking.action_confirm()

                # Réserver les produits
                picking.action_assign()

                # Valider automatiquement le picking (ou traiter le wizard si besoin)
                if not picking.button_validate():
                    wiz = self.env['stock.immediate.transfer'].search([('pick_ids', 'in', picking.id)], limit=1)
                    if wiz:
                        wiz.process()

            # 💸 3) Créer une note de frais pour chaque produit consommable
            # consumable_lines = order.order_line.filtered(lambda l: l.product_id and l.product_id.type == 'consu')
            #
            # for line in consumable_lines:
            #     if not self.env.user.employee_id:
            #         raise UserError(
            #             "L'utilisateur actuel n'est lié à aucun employé. Impossible de créer une note de frais.")
            #
            #     self.env['hr.expense'].create({
            #         'name': f"Achat consommable : {line.product_id.name}",
            #         'product_id': line.product_id.id,
            #         'total_amount_currency': line.price_subtotal,
            #         'tax_ids': [(6, 0, line.taxes_id.ids)],
            #         'quantity': line.product_qty,
            #         'employee_id': self.env.user.employee_id.id,
            #         'payment_mode': 'company_account',
            #         'date': fields.Date.today(),
            #     })

        return res

    def action_create_auto_payments(self):
        """Créer automatiquement les paiements pour les bons sélectionnés."""
        AccountPayment = self.env['account.payment']
        PaymentMethod = self.env.ref('account.account_payment_method_manual_in')

        # Vérifier si tous les bons sont confirmés (purchase ou done)
        not_confirmed = self.filtered(lambda o: o.state not in ['purchase', 'done'])
        if not_confirmed:
            raise UserError("⚠️ Il faut confirmer toutes les commandes avant de créer les paiements.")

        # Vérifier s'il y a des bons déjà payés
        already_paid = self.filtered(lambda o: o.amount_due_purchase <= 0)
        if already_paid:
            raise UserError("⚠️ Il existe déjà des bons totalement payés dans la sélection.")

        payments_created = 0

        for order in self:
            # Crée un paiement pour le montant dû
            payment_vals = {
                'payment_type': 'outbound',  # sortie d'argent
                'partner_id': order.partner_id.id,
                'amount': order.amount_due_purchase,
                'currency_id': order.currency_id.id,
                'payment_method_id': PaymentMethod.id,
                'date': fields.Date.today(),  # ✅ champ correct
                'purchase_order_id': order.id,
                'ref': f"Paiement auto - {order.name}",
            }

            payment = AccountPayment.create(payment_vals)
            payment.action_post()  # valider le paiement

            # Met à jour les montants
            order.amount_paid_purchase = order.amount_total
            order.amount_due_purchase = 0

            payments_created += 1

        if payments_created == 0:
            raise UserError("Aucun paiement n'a été créé.")

        # Notification de succès
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': "Paiements créés avec succès ✅",
                'message': f"{payments_created} paiement(s) ont été générés automatiquement.",
                'type': 'success',
                'sticky': False,
            }
        }

    @api.depends('payment_purchase_ids.amount', 'payment_purchase_ids.state')
    def _compute_amount_paid(self):
        """Calculer la somme des paiements validés"""
        for order in self:
            total_paid = sum(payment.amount for payment in order.payment_purchase_ids if payment.state == 'posted')
            order.amount_paid_purchase = total_paid

    @api.depends('amount_paid_purchase', 'amount_total')
    def _compute_amount_due(self):
        """Calcule le montant restant à payer."""
        for order in self:
            order.amount_due_purchase = order.amount_total - order.amount_paid_purchase

    @api.depends("payment_purchase_ids")
    def _compute_is_payment_term(self):
        """Détermine si le dernier paiement est en mode 'À Terme'"""
        for order in self:
            latest_payment = order.payment_purchase_ids.sorted(lambda p: p.create_date, reverse=True)[
                             :1]  # Dernier paiement
            order.is_payment_term_purchase = (
                latest_payment.payment_method_line_id.code == 'A-terme'
                if latest_payment else False
            )

    @api.depends('payment_purchase_ids')
    def _compute_payment_count(self):
        """Calcule le nombre de paiements effectués sur ce bon de commande"""
        for order in self:
            order.payment_count_purchase = len(order.payment_purchase_ids)

    def action_open_payments(self):
        """Ouvre la liste des paiements liés à ce bon de commande"""
        return {
            'name': "Paiements enregistrés",
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'domain': [('purchase_order_id', '=', self.id)],
            'context': {'default_purchase_order_id': self.id},
        }

    def action_register_payment(self):
        """Créer un paiement et l'affecter au bon de commande"""
        self.ensure_one()

        # Vérifier si le montant payé couvre déjà le total
        if self.amount_paid_purchase >= self.amount_total:
            raise ValidationError("Le paiement total a déjà été effectué pour ce bon de commande.")
        return {
            'name': "Enregistrer un paiement",
            'view_mode': 'form',
            'res_model': 'account.payment',
            'view_id': self.env.ref('account.view_account_payment_form').id,
            'type': 'ir.actions.act_window',
            'context': {
                'default_purchase_order_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_amount': self.amount_total - self.amount_paid_purchase,
                'default_currency_id': self.currency_id.id,
                'default_payment_type': 'outbound',
                'default_payment_method_id': self.env.ref('custom_project.account_payment_method_espece_in').id,
                'default_journal_id': self.env['account.journal'].search([('name', 'ilike', 'espèce')], limit=1).id,
                'default_cashbox_id': self.env['cashbox'].search([('name', '=', 'Caisse Espèce')], limit=1).id,
            },
            'target': 'new',
        }

    def action_create_grouped_invoice(self):
        """Créer une facture globale pour plusieurs bons d'achat sélectionnés"""
        if not self:
            raise UserError(_("Veuillez sélectionner au moins un bon de commande."))

        # Vérifier que tous les bons sont confirmés
        not_confirmed = self.filtered(lambda o: o.state not in ['purchase', 'done'])
        if not_confirmed:
            raise UserError(_("Tous les bons de commande doivent être confirmés.\nBons non confirmés: %s") %
                           ', '.join(not_confirmed.mapped('name')))

        # Vérifier que tous les bons ont le même fournisseur
        partners = self.mapped('partner_id')
        if len(partners) > 1:
            raise UserError(_("Tous les bons de commande doivent avoir le même fournisseur.\nFournisseurs trouvés: %s") %
                           ', '.join(partners.mapped('name')))

        # Vérifier que tous les bons ont un N° Facture
        orders_without_invoice_num = self.filtered(lambda o: not o.num_facture)
        if orders_without_invoice_num:
            raise UserError(_("Tous les bons de commande doivent avoir un N° Facture.\nBons sans N° Facture: %s") %
                           ', '.join(orders_without_invoice_num.mapped('name')))

        # Vérifier que tous les bons ont le même N° Facture
        invoice_numbers = set(self.mapped('num_facture'))
        if len(invoice_numbers) > 1:
            raise UserError(_("Tous les bons de commande doivent avoir le même N° Facture.\nN° Factures trouvés: %s") %
                           ', '.join(invoice_numbers))

        # Vérifier que les bons n'ont pas déjà une facture
        already_invoiced = self.filtered(lambda o: o.invoice_status == 'invoiced')
        if already_invoiced:
            raise UserError(_("Certains bons de commande ont déjà été facturés.\nBons déjà facturés: %s") %
                           ', '.join(already_invoiced.mapped('name')))

        # Récupérer les informations communes
        partner = partners[0]
        num_facture = list(invoice_numbers)[0]
        company = self[0].company_id
        currency = self[0].currency_id

        # Préparer les lignes de facture
        invoice_lines = []
        for order in self:
            for line in order.order_line:
                invoice_line_vals = {
                    'name': line.name,
                    'product_id': line.product_id.id,
                    'product_uom_id': line.product_uom.id,
                    'quantity': line.product_qty,
                    'price_unit': line.price_unit,
                    'tax_ids': [(6, 0, line.taxes_id.ids)],
                    'purchase_line_id': line.id,
                }
                invoice_lines.append((0, 0, invoice_line_vals))

        # Créer la facture fournisseur
        invoice_vals = {
            'move_type': 'in_invoice',
            'partner_id': partner.id,
            'currency_id': currency.id,
            'company_id': company.id,
            'invoice_date': fields.Date.today(),
            'ref': num_facture,
            'invoice_origin': ', '.join(self.mapped('name')),
            'invoice_line_ids': invoice_lines,
        }

        invoice = self.env['account.move'].create(invoice_vals)

        # Notification de succès
        return {
            'type': 'ir.actions.act_window',
            'name': _('Facture Fournisseur'),
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }


class AccountMoveInherit(models.Model):
    _inherit = 'account.move'

    purchase_order_ids = fields.Many2many(
        'purchase.order',
        string="Bons de commande",
        domain="[('partner_id', '=', partner_id), ('state', 'in', ['purchase', 'done']), ('invoice_status', '!=', 'invoiced')]",
    )

    @api.onchange('purchase_order_ids')
    def _onchange_purchase_order_ids(self):
        if self.move_type != 'in_invoice':
            return
        new_lines = []
        for order in self.purchase_order_ids:
            for line in order.order_line.filtered(lambda l: not l.display_type):
                new_lines.append((0, 0, {
                    'name': line.name,
                    'product_id': line.product_id.id,
                    'product_uom_id': line.product_uom.id,
                    'quantity': line.product_qty,
                    'price_unit': line.price_unit,
                    'tax_ids': [(6, 0, line.taxes_id.ids)],
                    'purchase_line_id': line.id,
                }))
        self.invoice_line_ids = [(5, 0, 0)] + new_lines


class AccountPaymentInherit(models.Model):
    _inherit = 'account.payment'

    purchase_order_id = fields.Many2one('purchase.order', string="Bon d'achat")
    amount_purchase = fields.Monetary(string="Montant du bon d'achat", related='purchase_order_id.amount_total',
                                      store=True)

    amount_due_purchase = fields.Monetary(string="Montant dû du bon d'achat",
                                          related='purchase_order_id.amount_due_purchase', store=True)

    amount_in_letters = fields.Char(string="Montant en lettres", compute='_compute_amount_in_letters')
    partner_id = fields.Many2one('res.partner', string='Fournisseur', required=True, change_default=True, tracking=True,
                                 check_company=True,
                                 help="Vous pouvez trouver un fournisseur par son nom, numéro de TVA , E-mail ou sa "
                                      "référence interne.",
                                 domain="[('contact_type','=','SUPPLIER')]")

    @api.depends('amount', 'currency_id')
    def _compute_amount_in_letters(self):
        """Convertit le montant en lettres (ex: 123 -> cent vingt-trois)"""

        def number_to_french(n: int) -> str:
            if n == 0:
                return "zéro"

            units = ["", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
                     "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
                     "dix-sept", "dix-huit", "dix-neuf"]
            tens = ["", "", "vingt", "trente", "quarante", "cinquante", "soixante", "soixante", "quatre-vingt",
                    "quatre-vingt"]

            def under_hundred(n):
                if n < 20:
                    return units[n]
                elif n < 100:
                    ten, unit = divmod(n, 10)
                    if ten in [7, 9]:
                        ten -= 1
                        unit += 10
                    result = tens[ten]
                    if unit > 0:
                        result += "-" + units[unit]
                    return result

            def under_thousand(n):
                hundred, rem = divmod(n, 100)
                words = ""
                if hundred > 0:
                    if hundred == 1:
                        words += "cent"
                    else:
                        words += units[hundred] + " cent"
                    if rem > 0:
                        words += " "
                if rem > 0:
                    words += under_hundred(rem)
                return words

            parts = []
            billions, n = divmod(n, 1_000_000_000)
            millions, n = divmod(n, 1_000_000)
            thousands, n = divmod(n, 1_000)

            if billions > 0:
                parts.append(under_thousand(billions) + " milliard" + ("s" if billions > 1 else ""))
            if millions > 0:
                parts.append(under_thousand(millions) + " million" + ("s" if millions > 1 else ""))
            if thousands > 0:
                if thousands == 1:
                    parts.append("mille")
                else:
                    parts.append(under_thousand(thousands) + " mille")
            if n > 0:
                parts.append(under_thousand(n))

            return " ".join(parts).strip()

        for payment in self:
            amount = int(payment.amount)
            payment.amount_in_letters = number_to_french(amount)

    # def write(self, vals):
    #     res = super().write(vals)
    #     for payment in self:
    #         if payment.purchase_order_id:
    #             payment.poush_notification()
    #     return res

    def poush_notification(self):
        self.ensure_one()
        print("\n✅ poush_notification() appelée pour :", self.name)

        # 1️⃣ Auteur = PARTNER tiers (OdooBot si dispo, sinon Admin partner)
        author_partner = self.env.ref('mail_bot.partner_odoo_bot', raise_if_not_found=False) \
                         or self.env.ref('base.partner_root')
        author_partner_id = author_partner.id

        # 2️⃣ Cibles = Farhi + Mesrane (partners)
        target_users = self.env['res.users'].sudo().search([
            '|',
            ('name', 'ilike', 'Farhi Souhila'),
            ('name', 'ilike', 'Mesrane Sabrina'),
        ])
        if not target_users:
            raise UserError("Aucun des managers (Farhi Souhila, Mesrane Sabrina) n'a pas ete trouve.")
        partner_ids = target_users.mapped('partner_id').ids

        # 3️⃣ Lien vers le paiement
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        paiement_url = f"{base_url}/web#id={self.id}&model=account.payment&view_type=form"

        # 🟢 récupérer le bon d'achat lié
        achat_name = self.purchase_order_id.name or "Bon d'achat inconnu"
        achat_amount = f"{self.amount} {self.currency_id.display_name}"

        # 4️⃣ Contenu HTML (➡️ lien cliquable + nom du bon d'achat)
        html_content = f"""
            <p><b>Bonjour,</b></p>
            <p>Un nouveau <b>paiement d'achat</b> est en attente de validation.</p>
            <p>
                <b>Bon d'achat :</b> {achat_name}<br/>
                <b>Montant :</b> {achat_amount}
            </p>
            <p>
                👉 <a href="{paiement_url}" target="_blank" rel="noopener">
                    Ouvrir le paiement {self.name or ''}
                </a>
            </p>
            <p>— L'équipe {self.company_id.name or ''}</p>
        """

        # 5️⃣ Canal Discuss (v17 = discuss.channel)
        Channel = self.env['discuss.channel']
        channel = Channel.sudo().search([('name', '=', 'Paiements à valider')], limit=1)
        if not channel:
            channel = Channel.sudo().create({
                'name': 'Paiements à valider',
                'description': 'Notifications des paiements à valider',
            })

        # 6️⃣ Ajouter Farhi et Mesrane au canal s'ils n'y sont pas encore
        for pid in partner_ids:
            if 'members' in channel._fields and pid not in channel.sudo().members.ids:
                channel.sudo().write({'members': [(4, pid)]})

        # 7️⃣ Poster le message (HTML, lien cliquable)
        mt_comment = self.env.ref('mail.mt_comment', raise_if_not_found=False)
        channel.sudo().message_post(
            author_id=author_partner_id,
            body=html_content,
            body_is_html=True,  # ✅ pour afficher correctement le HTML
            message_type='comment',
            partner_ids=partner_ids,
            subtype_id=mt_comment.id if mt_comment else False,
        )
        return True
