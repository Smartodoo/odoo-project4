from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_round
from markupsafe import Markup
from datetime import datetime

MSG_VERSEMENT_ST_LECTURE_SEULE = _("Accès refusé: Vous avez uniquement un accès en lecture sur les versements sous-traitants.")


class VersementSubcontractor(models.Model):
    _name = 'versement.subcontractor'
    _description = 'Versement Sous-traitant'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Référence", default='/')
    subcontractor_id = fields.Many2one('res.partner', string="Sous-traitant", required=True,
                                       domain="[('contact_type','=','SUBCONTRACTOR')]")
    amount = fields.Float(string="Montant à verser", required=True)
    amount_en_words = fields.Char(string="Montant en lettres", compute='_compute_amount_in_words', store=False)
    project_id = fields.Many2one('projects.associated', string="Projet", required=True,
                                 domain="[('original_subcontractor_id','=',subcontractor_id)]")
    situation_id = fields.Many2one('situation', string="Situation", required=True,
                                   domain="[('original_subcontractor_id', '=', subcontractor_id),"
                                          "('project_id1', '=', project_id),"
                                          "('state','in',['Non_paye','Partiellement_paye'])]")
    lots_id = fields.Many2many('custom.task.lots', string="Lot", required=True,
                               related='situation_id.lots_id')
    tasks_ids = fields.Many2many('situation.sous.traitants', string="Tâches", store=True,
                                 domain="[('montant_mois','!=',0),"
                                        "('situation_id','=',situation_id),"
                                        "('amount_task_due','>',0)]")
    date = fields.Date(string="Date", required=True, default=fields.Date.context_today)
    objet_versement = fields.Text(string="Objet du versement", compute='_onchange_tasks_ids', store=True)
    amount_paid = fields.Float(string="Montant dédja payé", related='situation_id.paid_amount', store=True)
    amount_due = fields.Float(string="Montant dû", related='situation_id.amount_residual', store=True)
    currency_id = fields.Many2one("res.currency", string="Devise", default=lambda self: self.env.company.currency_id)
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('registered', 'Enregistré'),
        ('confirmed', 'Validé'),
        ('done', 'Payé'),
    ], string="Statut", default='draft')
    company_id = fields.Many2one('res.company', string="Société", required=True,
                                 default=lambda self: self.env.company)
    tva_included = fields.Boolean(string="TVA incluse", default=False)
    r_g_st_included = fields.Boolean(string="RGS incluse", default=False)
    rgs_amount = fields.Monetary(string="RGS", related='situation_id.guarantee_retained', store=True, readonly=True)
    tva_amount = fields.Monetary(string="TVA", related='situation_id.tva', store=True, readonly=True)
    paiement_situation_ids = fields.Many2many(
        'paiement.situation',
        string="Paiements liés au versement",
        readonly=True,
        copy=False
    )
    user_id = fields.Many2one('res.users', 'user', default=lambda self: self.env.user, readonly=True)


    @api.depends('tasks_ids')
    def _onchange_tasks_ids(self):
        for record in self:
            if record.tasks_ids:
                textes = []
                for po in record.tasks_ids:
                    # Exemple : "Projet X : Montant 1000"
                    texte = f"{po.designation if po.designation else 'Tache'} : Montant {po.amount_distributed}"
                    textes.append(texte)
                record.objet_versement = f"Avance n°( ) et définitive sur decompte n°( ) du ({datetime.today().strftime('%d/%m/%Y')}) : " + "; ".join(
                    textes)
            else:
                record.objet_versement = "Avance n°( ) et définitive sur decompte n°( ) du ( ) :"

    @api.depends('amount')
    def _compute_amount_in_words(self):
        for rec in self:
            if rec.currency_id:
                amount_in_words = rec.currency_id.amount_to_text(rec.amount)
                rec.amount_en_words = amount_in_words
            else:
                rec.amount_en_words = ""

    # si une tache est selectionnée dédja dans un versement elle ne doit pas etre disponible dans un autre versement de la même situation
    @api.onchange('task_ids', 'situation_id')
    def _onchange_task_ids(self):
        for rec in self:
            other_versements = self.env['versement.subcontractor'].search([
                ('situation_id', '=', rec.situation_id.id),
            ])
            for task_id in rec.tasks_ids:
                for versement in other_versements:
                    if task_id.id in versement.tasks_ids.ids:
                        raise UserError(
                            f"La tâche {task_id.task_id.name} est déjà sélectionnée dans un autre versement pour cette situation.")

    # si tva_included est coché pour un versement d'une situation , alors il ne sera pas possible de le cocher pour un autre versement de la même situation et ceci en echangenat la situation avant d'enregistrer
    @api.onchange('tva_included', 'situation_id')
    def _onchange_tva_included_situation(self):
        for rec in self:
            if rec.tva_included:
                other_versements = self.env['versement.subcontractor'].search([
                    ('situation_id', '=', rec.situation_id.id),
                    ('tva_included', '=', True)
                ])
                if other_versements:
                    raise UserError("La TVA est déjà incluse dans un autre versement pour cette situation.")

    @api.onchange('r_g_st_included')
    def _onchange_rgs_included(self):
        for rec in self:
            if rec.r_g_st_included:
                other_versements = self.env['versement.subcontractor'].search([
                    ('situation_id', '=', rec.situation_id.id),
                    ('r_g_st_included', '=', True)
                ])
                if other_versements:
                    raise UserError("Le RGS est déjà inclus dans un autre versement pour cette situation.")

    @api.onchange('tva_included', 'tasks_ids', 'r_g_st_included')
    def _onchange_tva_included(self):
        for rec in self:
            total_distributed = sum(rec.tasks_ids.mapped('amount_distributed'))
            if rec.tva_included:
                rec.amount = float_round(total_distributed + rec.tva_amount, precision_rounding=0.01) - (
                    rec.rgs_amount if rec.r_g_st_included else 0)
            else:
                rec.amount = float_round(total_distributed, precision_rounding=0.01) - (
                    rec.rgs_amount if rec.r_g_st_included else 0)

    @api.depends('tasks_ids', 'tva_included', 'tva')
    def _compute_amounts(self):
        for rec in self:
            total_distributed = sum(rec.tasks_ids.mapped('amount_distributed'))
            if rec.tva_included:
                rec.amount = float_round(total_distributed + rec.tva_amount, precision_rounding=0.01)
            else:
                rec.amount = float_round(total_distributed, precision_rounding=0.01)

    @api.model
    def create(self, vals):
        if self.env.user.has_group('custom_project.group_versement_st_lecture_seule'):
            raise UserError(MSG_VERSEMENT_ST_LECTURE_SEULE)
        if vals.get('name', '/') in (False, '/', ''):
            vals['name'] = self.env['ir.sequence'].next_by_code('versement.subcontractor')
        return super().create(vals)

    def write(self, vals):
        if self.env.user.has_group('custom_project.group_versement_st_lecture_seule'):
            raise UserError(MSG_VERSEMENT_ST_LECTURE_SEULE)
        return super().write(vals)

    # interdir la suppression d'un versement en état 'done'
    def unlink(self):
        if self.env.user.has_group('custom_project.group_versement_st_lecture_seule'):
            raise UserError(MSG_VERSEMENT_ST_LECTURE_SEULE)
        for versement in self:
            if versement.state == 'done':
                raise UserError("Un versement payé ne peut pas être supprimé.")
            if versement.state == 'confirmed':
                raise UserError(
                    "Un versement validé ne peut pas être supprimé, il doit d'abord être remis à l'état brouillon.")
        return super().unlink()

    def _check_amount(self):
        for rec in self:
            for task in rec.tasks_ids:
                if task.amount_distributed < 0:
                    raise UserError("Le montant réparti ne peut pas être négatif.")
                if task.amount_distributed > task.montant_mois:
                    raise UserError("Le montant réparti ne peut pas dépasser le montant de la tâche.")
            total_distributed = sum(rec.tasks_ids.mapped('amount_distributed'))
            if rec.tva_included and total_distributed + rec.tva_amount < rec.amount and not rec.r_g_st_included:
                raise UserError("Le montant total réparti doit être égal au montant à verser (avec TVA si applicable).")
            if rec.tva_included and rec.r_g_st_included and total_distributed + rec.tva_amount - rec.rgs_amount < rec.amount:
                raise UserError(
                    "Le montant total réparti doit être égal au montant à verser (avec TVA et RGS si applicable).")
            if not rec.tva_included and rec.r_g_st_included and total_distributed - rec.rgs_amount < rec.amount:
                raise UserError("Le montant total réparti doit être égal au montant à verser (avec RGS si applicable).")
            if not rec.tasks_ids:
                raise UserError("Au moins une tâche doit être sélectionnée pour le versement.")
            if rec.amount <= 0:
                raise UserError("Le montant du versement doit être supérieur à zéro.")

    def action_register(self):
        """Enregistrer le versement et notifier le directeur technique"""
        for versement in self:
            versement._check_amount()
            if versement.amount > versement.situation_id.net_amount:
                raise UserError("Le montant du versement ne peut pas dépasser le montant total de la situation.")
            if versement.amount_paid + versement.amount > versement.situation_id.net_amount:
                raise UserError("Le montant total payé ne peut pas dépasser le montant total de la situation.")
            versement.state = 'registered'
            # Notifier le directeur technique via le canal Discuss
            channel = self.env.ref('custom_project.channel_versement_confirmation', raise_if_not_found=False)
            dt_user = self.env['res.users'].sudo().search([('login', '=', 'technique@gmail.com')], limit=1)
            if channel and dt_user and dt_user.partner_id:
                # S'assurer que le DT est membre du canal
                if dt_user.partner_id not in channel.channel_partner_ids:
                    channel.sudo().channel_partner_ids = [(4, dt_user.partner_id.id)]
                base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                versement_url = '%s/web#id=%d&model=versement.subcontractor&view_type=form' % (base_url, versement.id)
                body_html = Markup(
                    "<b>Versement à confirmer</b><br/>"
                    "Référence : <b>%s</b><br/>"
                    "Sous-traitant : <b>%s</b><br/>"
                    "Montant : <b>%.2f DA</b><br/>"
                    "Enregistré par : <b>%s</b><br/><br/>"
                    "<a href='%s' style='display: inline-block; padding: 8px 16px; "
                    "background-color: #875A7B; color: white; text-decoration: none; "
                    "border-radius: 4px; font-weight: bold;'>Voir le versement</a>"
                ) % (
                    versement.name,
                    versement.subcontractor_id.name,
                    versement.amount,
                    self.env.user.name,
                    versement_url,
                )
                channel.message_post(
                    body=body_html,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                )

    def action_confirm(self):
        """Confirmer le versement (directeur technique uniquement)"""
        for versement in self:
            versement.action_done()
            versement.state = 'confirmed'

    def action_set_to_draft(self):
        for versement in self:
            if versement.state == 'done':
                raise UserError("Un versement payé ne peut pas être remis à l'état brouillon.")
            versement.state = 'draft'

    def action_done(self):
        for versement in self:
            # 1) validations basiques
            if not versement.situation_id:
                raise UserError("Aucune situation liée au versement.")
            versement._check_amount()

            # 2) récupérer une méthode de paiement : priorité à celle référencée dans ton module
            payment_method = self.env.ref('custom_project.account_payment_method_espece_out', raise_if_not_found=False)
            if not payment_method:
                payment_method = self.env['account.payment.method'].search([], limit=1)
            if not payment_method:
                raise UserError(
                    "Aucune méthode de paiement trouvée. Créez au moins une méthode de paiement ou ajoutez la référence 'custom_project.account_payment_method_espece_out'.")
            # Get the actual project from the situation (custom.project)
            project_id = versement.situation_id.project_id
            if not project_id:
                raise UserError("Aucun projet trouvé pour cette situation.")
            # 3) préparer les valeurs du paiement
            paiement_vals = {
                'situation_id': versement.situation_id.id,
                'reference': versement.name or f"Versement-{versement.id or ''}",
                'partner_id': versement.subcontractor_id.id,
                'project_id': project_id.id,
                'payment_date': fields.Date.context_today(versement),
                'amount_paid': versement.amount,
                'payment_method_id': payment_method.id,
                'company_id': versement.company_id.id,
                'status': 'not_paid',  # marquer payé pour que les compute côté Situation le prenne en compte
            }

            # 4) création du paiement
            try:
                paiement = self.env['paiement.situation'].create(paiement_vals)
            except Exception as e:
                raise UserError(
                    "Erreur lors de la création automatique du paiement. "
                    "Vérifie le modèle 'paiement.situation' et les champs requis.\n"
                    f"Erreur technique: {e}"
                )

            # 5) envoyer la notification de paiement à valider
            versement.situation_id.poush_notification()

            versement.paiement_situation_ids = [(4, paiement.id)]
            # poster message de trace (optionnel)
            versement.situation_id.message_post(
                body=(f"Paiement (id: {paiement.id}) créé en brouillon via Versement {versement.name}."),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

        return True

    def action_validate_paiements(self):
        """Valide tous les paiements créés pour ce versement (admin ou Mesrane Sabrina)."""
        for versement in self:
            # sécurité : l'utilisateur courant doit être admin ou Mesrane Sabrina
            is_admin = self.env.user.has_group('base.group_system')
            is_mesrane = self.env.user.name == 'Mesrane Sabrina'
            if not is_admin and not is_mesrane:
                raise UserError("Seul un administrateur peut valider ce versement.")

            if not versement.paiement_situation_ids:
                raise UserError("Aucun paiement à valider pour ce versement.")

            # valider chaque paiement créé
            for paiement in versement.paiement_situation_ids:
                # si la méthode normalisée existe, on l'appelle
                if hasattr(paiement, 'action_validate_payment'):
                    try:
                        paiement.action_validate_payment()
                    except Exception as e:
                        # si échec, on lève une erreur pour éviter état incohérent
                        raise UserError(f"Erreur lors de la validation du paiement id {paiement.id}: {e}")

            # une fois tous validés, marquer le versement comme 'done'
            versement.state = 'done'

            # poster message final
            versement.situation_id.message_post(
                body=(
                    f"Les paiements liés au Versement {versement.name} ont été validés (paiements: {versement.paiement_situation_ids.ids}).")
            )

        return True

    def action_preview_report(self):
        """Prévisualiser le rapport dans un nouvel onglet"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/custom_project.report_versement_subcontractor_document/%s' % self.id,
            'target': 'new',
        }


class AmountDistribution(models.Model):
    _name = 'amount.distribution'
    _description = 'Répartition du montant'

    versement_id = fields.Many2one('versement.subcontractor', string="Versement Sous-traitant")
    task_id = fields.Many2one('partner.task.line', string="Tâche", required=True)
    task_amount = fields.Float(string="Montant de la tâche", related='task_id.total_price', store=True)
    amount = fields.Float(string="Montant réparti", required=True)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user.has_group('custom_project.group_versement_st_lecture_seule'):
            raise UserError(MSG_VERSEMENT_ST_LECTURE_SEULE)
        return super().create(vals_list)

    def write(self, vals):
        if self.env.user.has_group('custom_project.group_versement_st_lecture_seule'):
            raise UserError(MSG_VERSEMENT_ST_LECTURE_SEULE)
        return super().write(vals)

    def unlink(self):
        if self.env.user.has_group('custom_project.group_versement_st_lecture_seule'):
            raise UserError(MSG_VERSEMENT_ST_LECTURE_SEULE)
        return super().unlink()
