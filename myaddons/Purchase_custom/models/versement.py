from odoo import api, fields, models, _
from datetime import datetime
from num2words import num2words
from odoo.exceptions import UserError
from odoo.tools import float_round

MSG_VERSEMENT_LECTURE_SEULE = _("Accès refusé: Vous avez uniquement un accès en lecture sur les versements fournisseurs.")


class Versement(models.Model):
    _name = 'versement.versement'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Référance', readonly=True, default='/')
    fournisseur_id = fields.Many2one(
        'res.partner',
        string="Fournisseur",
        domain="[('contact_type','=','SUPPLIER')]",
    )
    montant_verser = fields.Float(string="Montant à versé", required=True)

    purchase_order_ids = fields.Many2many(
        'purchase.order',
        string="Bons d'achats",
        domain="[('partner_id', '=', fournisseur_id), ('state', '=', 'purchase'), ('amount_due_purchase', '!=', 0)]"
    )
    project_ids = fields.Many2many(
        'custom.project',
        string="Projets associés",
        compute="_compute_projects",
        store=True
    )

    date = fields.Date(string="Date", default=datetime.today())
    lettre = fields.Char(string="En lettres", compute="_compute_amount_in_words", store=True)

    distribution_montant_ids = fields.One2many(
        'distribution.montant',
        'versement_id',
        string="Distribution des montants"
    )

    objet = fields.Text(string="Objet de versement", compute="_compute_objet", store=True)

    montant_deja_paye = fields.Float(string="Montant deja payé", compute="_compute_montant_deja_paye", store=True)

    montant_total = fields.Float(string="Montant Total", compute="_compute_montant_total", store=True)

    montant_reste = fields.Float(string="Reste", compute="_compute_montant_reste", store=True)

    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        default=lambda self: self.env.company.currency_id
    )

    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('done', 'Confirmé'),
        ('payed', 'Payé')
    ], string="Statut", default='draft', readonly=True)

    paiement_ids = fields.Many2many('account.payment', string="Paiements créés")
    lot = fields.Char(string="Lot")
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)

    def _auto_select_purchase_orders(self):
        """Sélection automatique des bons d'achat du fournisseur
           triés du plus petit reste à payer au plus grand"""
        self.ensure_one()

        if not self.fournisseur_id:
            self.purchase_order_ids = False
            self.project_ids = False
            return

        # récupérer les bons d'achat
        bons = self.env['purchase.order'].search([
            ('partner_id', '=', self.fournisseur_id.id),
            ('state', '=', 'purchase'),
            ('amount_due_purchase', '>', 0),
        ]).sorted(lambda po: po.amount_due_purchase)

        # affecter les bons
        self.purchase_order_ids = [(6, 0, bons.ids)]

        # remplir le champ project_ids à partir des projets des bons d'achat
        self.project_ids = [(6, 0, bons.mapped('project_id').ids)]

    @api.depends('purchase_order_ids')
    def _compute_objet(self):
        for record in self:
            if record.purchase_order_ids:
                textes = []
                for po in record.purchase_order_ids:
                    texte = f"{po.project_id.name if po.project_id else 'Projet'} : Montant {po.amount_total}"
                    textes.append(texte)
                record.objet = f"Avance n°( ) et définitive sur situation arrêtée le ({datetime.today().strftime('%d/%m/%Y')}) : " + "; ".join(
                    textes)
            else:
                record.objet = "Avance n°( ) et définitive sur situation arrêtée le ( ) :"

    def unlink(self):
        if self.env.user.has_group('Purchase_custom.group_versement_lecture_seule'):
            raise UserError(MSG_VERSEMENT_LECTURE_SEULE)
        for versement in self:
            if versement.state == 'payed':
                raise UserError("Un versement payé ne peut pas être supprimé.")
            if versement.state == 'done':
                raise UserError(
                    "Un versement validé ne peut pas être supprimé, il doit d'abord être remis à l'état brouillon.")
        return super().unlink()

    def write(self, vals):
        if self.env.user.has_group('Purchase_custom.group_versement_lecture_seule'):
            raise UserError(MSG_VERSEMENT_LECTURE_SEULE)
        return super().write(vals)

    @api.onchange('purchase_order_ids')
    def _get_totals_from_purchases(self):
        for rec in self:
            total = sum(rec.purchase_order_ids.mapped('amount_total'))
            rec.montant_total = total
            montant_deja_paye = sum(rec.purchase_order_ids.mapped('amount_paid_purchase'))
            rec.montant_deja_paye = montant_deja_paye
            montant_reste = total - montant_deja_paye
            rec.montant_reste = montant_reste

    @api.onchange('distribution_montant_ids')
    def _onchange_distribution_montant_ids(self):
        for rec in self:
            total_distributed = sum(rec.distribution_montant_ids.mapped('montant'))
            rec.montant_verser = float_round(total_distributed, precision_rounding=0.01)

    @api.model
    def create(self, vals):
        if self.env.user.has_group('Purchase_custom.group_versement_lecture_seule'):
            raise UserError(MSG_VERSEMENT_LECTURE_SEULE)
        if vals.get('name', '/') in (False, '/', ''):
            vals['name'] = self.env['ir.sequence'].next_by_code('versement.versement')
        return super(Versement, self).create(vals)

    @api.model
    def _get_vendors_in_purchase(self):
        """Retourne la liste des fournisseurs ayant au moins un purchase.order"""
        vendors = self.env['purchase.order'].search([]).mapped('partner_id.id')
        return vendors

    @api.onchange('fournisseur_id')
    def _onchange_fournisseur_id(self):
        for rec in self:
            rec._auto_select_purchase_orders()

    # Méthode interne : distribution de montant automatiquement
    @api.model
    def _distribuer_montant(self):
        if not self.purchase_order_ids:
            # Aucun bon sélectionné, mettre les montants à 0
            for line in self.distribution_montant_ids:
                line.montant = 0
            return

        montant_restant = self.montant_verser if self.montant_verser else 0

        # Trier les lignes par montant total croissant
        lignes_tries = self.distribution_montant_ids.sorted(lambda l: l.total)

        for line in lignes_tries:
            if montant_restant <= 0:
                line.montant = 0
                continue

            if montant_restant >= line.total:
                line.montant = line.total
                montant_restant -= line.total
            else:
                line.montant = montant_restant
                montant_restant = 0

    #  créer les lignes + redistribuer
    @api.onchange('purchase_order_ids')
    def _onchange_purchase_orders(self):
        # Vider les anciennes lignes
        self.distribution_montant_ids = [(5, 0, 0)]

        # Créer les lignes pour tous les bons sélectionnés
        lignes = []
        for bon in self.purchase_order_ids:
            lignes.append((0, 0, {
                'purchase_id': bon.id,
                'total': bon.amount_due_purchase,
                'montant': 0.0,
            }))
        self.distribution_montant_ids = lignes

        # Redistribuer automatiquement si le montant a déjà été saisi
        self._distribuer_montant()

    # Onchange sur le montant à verser : redistribuer

    @api.onchange('montant_verser')
    def _onchange_montant_verser(self):
        for rec in self:
            if not rec.purchase_order_ids:
                rec._auto_select_purchase_orders()
            rec._distribuer_montant()

    @api.depends('montant_verser', 'currency_id')
    def _compute_amount_in_words(self):
        for rec in self:
            if rec.currency_id:
                amount_in_words = rec.currency_id.amount_to_text(rec.montant_verser)
                rec.lettre = amount_in_words
            else:
                rec.lettre = ""

    # calculer le montant de tous les bon confirmé associer a un fournisseur
    @api.depends('fournisseur_id')
    def _compute_montant_total(self):
        for rec in self:
            if rec.fournisseur_id:
                bons = self.env['purchase.order'].search([('id', 'in', rec.purchase_order_ids.ids)]).mapped(
                    'amount_total')
                rec.montant_total = sum(bons) if bons else 0.0

    @api.depends('fournisseur_id')
    def _compute_montant_deja_paye(self):
        """Calcule le total des paiements déjà effectués pour le fournisseur sélectionné"""
        for rec in self:
            if not rec.fournisseur_id:
                rec.montant_deja_paye = 0.0
                continue

            # Rechercher tous les paiements validés pour ce fournisseur
            # paiements = self.env['account.payment'].search([
            #     ('partner_id', '=', rec.fournisseur_id.id),
            #     ('state', '=', 'posted')
            # ])
            paiements = self.env['purchase.order'].search([
                ('id', 'in', rec.purchase_order_ids.ids)
            ]).mapped('amount_paid_purchase')

            # Total payé ou zéro si aucun paiement
            rec.montant_deja_paye = sum(paiements) if paiements else 0.0

    @api.depends('montant_total', 'montant_verser', 'montant_deja_paye')
    def _compute_montant_reste(self):
        for rec in self:
            rec.montant_reste = rec.montant_total - (rec.montant_deja_paye + rec.montant_verser)

    def _check_amount(self):
        for rec in self:
            for purchase in rec.distribution_montant_ids:
                if purchase.montant < 0:
                    raise UserError("Le montant réparti ne peut pas être négatif.")
                if purchase.montant > purchase.total:
                    raise UserError("Le montant réparti ne peut pas dépasser le montant de bon.")
            if not rec.distribution_montant_ids:
                raise UserError("Au moins une bon doit être sélectionnée pour le versement.")
            if rec.montant_verser <= 0:
                raise UserError("Le montant du versement doit être supérieur à zéro.")

    def action_set_draft(self):
        for versement in self:
            if versement.state == 'payed':
                raise UserError("Un versement payé ne peut pas être remis à l'état brouillon.")
            versement.state = 'draft'

    def action_confirmer_versement(self):
        for versement in self:
            versement._check_amount()
            if versement.montant_verser > versement.montant_total:
                raise UserError("Le montant du versement ne peut pas dépasser le montant total.")
            if versement.montant_deja_paye + versement.montant_verser > versement.montant_total:
                raise UserError("Le montant total payé ne peut pas dépasser le montant total de la situation.")
            versement.action_payed()
            versement.poush_notification()
            versement.state = 'done'

    def action_payed(self):
        # on cliquant sur le bouton payé les bons choisis sur le versement seront payé avec le montant correspondant puis le versement sera en état payé
        for versement in self:
            versement._check_amount()
            payment_method = self.env.ref('custom_project.account_payment_method_espece_out', raise_if_not_found=False)
            if not payment_method:
                payment_method = self.env['account.payment.method'].search([], limit=1)
            if not payment_method:
                raise UserError(
                    "Aucune méthode de paiement trouvée. Créez au moins une méthode de paiement ou ajoutez la référence 'custom_project.account_payment_method_espece_out'.")
            paiement_ids = self.env['account.payment']
            for line in versement.distribution_montant_ids:
                paiement_vals = {
                    'partner_id': versement.fournisseur_id.id,
                    'amount': line.montant,
                    'payment_type': 'outbound',
                    'payment_method_id': payment_method.id,
                    'amount_due_purchase': versement.montant_reste,
                    'amount_in_letters': versement.lettre,
                    'ref': f"Paiement pour bon d'achat {line.purchase_id.name} via versement {versement.name}",
                    'purchase_order_id': line.purchase_id.id,
                    'cashbox_id': self.env['cashbox'].search([('name', '=', 'Caisse Espèce')], limit=1).id,

                }
                paiement = self.env['account.payment'].create(paiement_vals)
                paiement_ids |= paiement
            versement.paiement_ids = paiement_ids

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

        # 3️⃣ Lien vers le versement
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        paiement_url = f"{base_url}/web#id={self.id}&model=versement.versement&view_mode=form"

        # 🟢 récupérer le bon d'achat lié
        versement_name = self.name or "Versement inconnu"
        versement_amount = f"{self.montant_verser} {self.currency_id.display_name}"

        # 4️⃣ Contenu HTML (➡️ lien cliquable + nom du bon d'achat)
        html_content = f"""
               <p><b>Bonjour,</b></p>
               <p>Un nouveau <b>paiement de versement </b> est en attente de validation.</p>
               <p>
                   <b>Versement :</b> {versement_name}<br/>
                   <b>Montant :</b> {versement_amount}
               </p>
               <p>
                   👉 <a href="{paiement_url}" target="_blank" rel="noopener">
                       Ouvrir le versement {self.name or ''}
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
                'description': 'Notifications des paiements(versements) à valider',
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

    def action_payed_versement(self):
        for versement in self:
            is_admin = self.env.user.has_group('base.group_system')
            is_mesrane = self.env.user.name == 'Mesrane Sabrina'
            if not is_admin and not is_mesrane:
                raise UserError("Seul un administrateur peut valider ce versement.")

            if not versement.paiement_ids:
                raise UserError("Aucun paiement à valider pour ce versement.")

            # Valider tous les paiements créés (sudo pour contourner les restrictions lecture seule)
            for paiement in versement.paiement_ids:
                paiement.sudo().action_post()
            purchase_order_ids = versement.mapped('purchase_order_ids').ids
            caisse_expense_supplier = self.env['caisse.expense.supplier'].sudo().search(
                [('purchase_id', 'in', purchase_order_ids)])
            if caisse_expense_supplier:
                caisse_expense_supplier.state = 'approuve'
            # Mettre le versement en état payé
            versement.sudo().state = 'payed'

    def action_preview_report(self):
        """Prévisualiser le rapport dans un nouvel onglet"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/Purchase_custom.report_versement_fournisseur_document/%s' % self.id,
            'target': 'new',
        }


class ResPartner(models.Model):
    _inherit = 'res.partner'

    versement_count = fields.Integer(string="versements", compute='_compute_nombre_versement')
    payment_count = fields.Integer(string="paiements", compute='_compute_nombre_payments')
    versement_sub_count = fields.Integer(string="Versements Sous-traitants", compute='_compute_versement_sub_count')
    credit_supplier = fields.Float(string="Crédit Fournisseur", compute='_compute_credit_supplier')
    credit_subcontractor = fields.Float(string="Crédit Sous-traitant", compute='_compute_credit_subcontractor')
    payment_count_sub = fields.Integer(string="Paiements Sous-traitants", compute='_compute_nombre_payments_sub')

    def _compute_nombre_payments_sub(self):
        for partner in self:
            partner.payment_count_sub = self.env['paiement.situation'].search_count(
                [('partner_id', '=', partner.id)])

    def _compute_versement_sub_count(self):
        for partner in self:
            partner.versement_sub_count = self.env['versement.subcontractor'].search_count(
                [('subcontractor_id', '=', partner.id)])

    def open_versements_subcontractor(self):
        self.ensure_one()
        return {
            'name': "Versements Sous-traitants",
            'type': 'ir.actions.act_window',
            'res_model': 'versement.subcontractor',
            'view_mode': 'tree,form',
            'domain': [('subcontractor_id', '=', self.id)],
            'context': {'default_subcontractor_id': self.id},
        }

    @api.depends('versement_sub_count', 'payment_count')
    def _compute_credit_subcontractor(self):

        for partner in self:
            total_payments = sum(self.env['paiement.situation'].search(
                [('partner_id', '=', partner.id), ('status', '=', 'paid')]).mapped('amount_paid'))
            total_situations = sum(self.env['situation'].search(
                [('original_subcontractor_id', '=', partner.id)]).mapped('net_amount'))
            partner.credit_subcontractor = total_situations - total_payments

    @api.depends('versement_count', 'payment_count')
    def _compute_credit_supplier(self):
        for partner in self:
            total_bons = sum(self.env['purchase.order'].search(
                [('partner_id', '=', partner.id), ('state', '=', 'purchase')]).mapped('amount_total'))
            total_payments = sum(self.env['account.payment'].search(
                [('partner_id', '=', partner.id),
                 ('payment_type', '=', 'outbound'),
                 ('state', '=', 'posted')
                 ]).mapped('amount'))
            partner.credit_supplier = total_bons - total_payments

    def _compute_nombre_versement(self):
        for partner in self:
            partner.versement_count = self.env['versement.versement'].search_count(
                [('fournisseur_id', '=', partner.id)])

    def _compute_nombre_payments(self):
        for partner in self:
            partner.payment_count = self.env['account.payment'].search_count(
                [('partner_id', '=', partner.id), ('payment_type', '=', 'outbound')])

    def open_versement_supplier(self):
        self.ensure_one()
        return {
            'name': "Versements",
            'type': 'ir.actions.act_window',
            'res_model': 'versement.versement',
            'view_mode': 'tree,form',
            'domain': [('fournisseur_id', '=', self.id)],
            'context': {'default_fournisseur_id': self.id},
        }

    def open_payments_supplier(self):
        self.ensure_one()
        return {
            'name': "Paiements",
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id), ('payment_type', '=', 'outbound')],
            'context': {'default_partner_id': self.id, 'default_payment_type': 'outbound'},
        }

    def open_payments_subcontractor(self):
        self.ensure_one()
        return {
            'name': "Paiements Sous-traitants",
            'type': 'ir.actions.act_window',
            'res_model': 'paiement.situation',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
