from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

import logging

_logger = logging.getLogger(__name__)

MSG_SITUATION_LECTURE_SEULE = _("Accès refusé: Vous avez uniquement un accès en lecture sur les situations.")


class SituationSousTraitant(models.Model):
    _name = "situation.sous.traitants"
    _description = "la situation des articles pour chaque sous traitant"
    _order = "sequence, id"
    _rec_name = 'designation'

    sequence = fields.Integer(string="Séquence", default=10)
    num = fields.Char(string="N°")
    designation = fields.Char(string="Désignation")
    unit = fields.Many2one("uom.uom", string="Unité")
    qty_marche = fields.Float(string="Q.marché", help=("Quantité du marché"))
    qty_precedente = fields.Float(string="Q.précédente", help=("Quantité de la situation précédente"))
    qty_du_mois = fields.Float(string="Q.mois", help=("Quantité réalisée du mois en cours"))
    qty_cummulee = fields.Float(string="Q.cumulée", help=("Quantité totale réalisée jusqu'à ce jour"),
                                compute='_compute_totals', store=True)
    prix_unitaire_convention = fields.Float(string="P.U", digits=(12, 2), help=("Prix unitaire selon la convention"))
    montant_marche = fields.Float(string="M.marché", help=("Montant total du marché"), compute='_compute_totals',
                                  store=True)
    montant_precedent = fields.Float(string="M.précédent", help=("Montant total de la situation précédente"),
                                     compute='_compute_totals', store=True)
    montant_mois = fields.Float(string="M.mois", help=("Montant total réalisé du mois en cours"),
                                compute='_compute_totals', store=True)
    montant_cummulee = fields.Float(string="M.cumulée", help=("Montant total réalisé jusqu'à ce jour"),
                                    compute='_compute_totals', store=True)
    amount_distributed = fields.Float(string="Montant réparti")
    amount_task_due = fields.Float(string="difference", compute='compute_amount_task_due', store=True)
    project_id = fields.Many2one(related="situation_id.project_id", string="Projet", store=True)
    original_subcontractor_id = fields.Many2one(related="situation_id.original_subcontractor_id",
                                                string="Sous-traitant d'origine",
                                                domain="[('contact_type','=','SUBCONTRACTOR')]", store=True)
    situation_id = fields.Many2one("situation", string="Situation", required=True)
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user)
    type_tasks = fields.Selection([("primary", "Service"), ("secondary", "Logments")], default="primary",
                                  string="Source import")
    qty_exceeds_marche = fields.Boolean(
        string="Dépasse la quantité du marché",
        compute='_compute_qty_exceeds_marche',
        store=False,
        help="Vrai si la quantité du mois ou la quantité cumulée dépasse la quantité du marché.",
    )

    @api.depends('qty_du_mois', 'qty_precedente', 'qty_marche')
    def _compute_qty_exceeds_marche(self):
        for rec in self:
            if not rec.qty_marche:
                rec.qty_exceeds_marche = False
                continue
            qty_cummulee = (rec.qty_precedente or 0.0) + (rec.qty_du_mois or 0.0)
            rec.qty_exceeds_marche = (
                float_compare(rec.qty_du_mois or 0.0, rec.qty_marche, precision_digits=2) > 0
                or float_compare(qty_cummulee, rec.qty_marche, precision_digits=2) > 0
            )

    @api.onchange('qty_du_mois', 'qty_precedente', 'qty_marche')
    def _onchange_qty_du_mois(self):
        if not self.qty_marche or not self.qty_du_mois:
            return
        if float_compare(self.qty_du_mois, self.qty_marche, precision_digits=2) > 0:
            return {
                'warning': {
                    'title': _("Quantité du marché dépassée"),
                    'message': _(
                        "La quantité du mois (%.2f) dépasse la quantité du marché (%.2f) pour l'article '%s'."
                    ) % (self.qty_du_mois, self.qty_marche, self.designation or ''),
                }
            }
        qty_cummulee = (self.qty_precedente or 0.0) + (self.qty_du_mois or 0.0)
        if float_compare(qty_cummulee, self.qty_marche, precision_digits=2) > 0:
            return {
                'warning': {
                    'title': _("Quantité du marché dépassée"),
                    'message': _(
                        "La quantité cumulée (%.2f) dépasse la quantité du marché (%.2f) pour l'article '%s'."
                    ) % (qty_cummulee, self.qty_marche, self.designation or ''),
                }
            }

    @api.onchange('qty_marche')
    def _onchange_qty_marche_vs_projet(self):
        """Avertit si qty_marche de la situation dépasse la quantité du marché du projet (non-bloquant)."""
        if not self.qty_marche or not self.situation_id or not self.designation:
            return
        assoc = self.env['projects.associated'].search([
            ('project_id', '=', self.situation_id.project_id.id),
            ('original_subcontractor_id', '=', self.situation_id.original_subcontractor_id.id),
        ], limit=1)
        if not assoc:
            return
        task_line = assoc.task_line_ids.filtered(
            lambda l: l.task_id and l.task_id.name == self.designation
        )
        if task_line:
            qty_projet = task_line[0].quantity or 0.0
            if qty_projet and float_compare(self.qty_marche, qty_projet, precision_digits=2) > 0:
                return {
                    'warning': {
                        'title': _("Quantité du marché dépassée"),
                        'message': _(
                            "La quantité convention (%.2f) dépasse la quantité du marché du projet (%.2f) pour l'article '%s'."
                        ) % (self.qty_marche, qty_projet, self.designation),
                    }
                }

    @api.depends('amount_distributed', 'montant_mois')
    def compute_amount_task_due(self):
        for rec in self:
            rec.amount_task_due = rec.montant_mois - rec.amount_distributed

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user.has_group('custom_project.group_situation_lecture_seule'):
            raise UserError(MSG_SITUATION_LECTURE_SEULE)
        recs = super().create(vals_list)

        Finale = self.env['situation.final']
        for rec in recs:
            art_id = rec.designation
            domain = [
                ('project_id', '=', rec.project_id.id),
                ('designation2', '=', art_id),
            ]
            finale_rec = Finale.search(domain, limit=1)
            if not finale_rec:
                Finale.create({
                    'project_id': rec.project_id.id,
                    'designation2': art_id,
                    'quantity_marche': rec.qty_marche,
                    'quantity_cumulee': rec.qty_cummulee,
                    'montant_marche': rec.montant_marche,
                    'montant_cumulee': rec.montant_cummulee,
                })
            else:
                finale_rec.quantity_marche += rec.qty_marche
                finale_rec.quantity_cumulee += rec.qty_cummulee
                finale_rec.montant_marche += rec.montant_marche
                finale_rec.montant_cumulee += rec.montant_cummulee
        return recs

    def write(self, vals):
        if self.env.user.has_group('custom_project.group_situation_lecture_seule'):
            raise UserError(MSG_SITUATION_LECTURE_SEULE)
        return super().write(vals)

    def unlink(self):
        if self.env.user.has_group('custom_project.group_situation_lecture_seule'):
            raise UserError(MSG_SITUATION_LECTURE_SEULE)
        return super().unlink()

    @api.depends('qty_precedente', 'qty_du_mois',
                 'qty_marche', 'prix_unitaire_convention')
    def _compute_totals(self):
        for rec in self:
            rec.qty_cummulee = rec.qty_precedente + rec.qty_du_mois
            rec.montant_marche = rec.qty_marche * rec.prix_unitaire_convention
            rec.montant_precedent = rec.qty_precedente * rec.prix_unitaire_convention
            rec.montant_mois = rec.qty_du_mois * rec.prix_unitaire_convention
            rec.montant_cummulee = rec.qty_cummulee * rec.prix_unitaire_convention


class SituationReport(models.AbstractModel):
    _name = 'report.custom_project.report_situation_document'
    _description = 'Rapport PDF Situation'

    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user)

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['situation'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'situation',
            'docs': docs, }


class SituationFinale(models.Model):
    _name = "situation.final"
    _description = "Situation finale des articles"

    # article = fields.Many2one("stock.articles", string="Article", domain="[('project_id','=',project_id)]")
    designation2 = fields.Char(string="Article")
    quantity_marche = fields.Float(string="Qty marché", help=("Quantité du marché"))
    quantity_cumulee = fields.Float(string="Qty cummulée", help=("Quantité totale réalisée jusqu'à ce jour"))
    montant_marche = fields.Float(string="M.T du marché", help=("Montant total du marché"))
    montant_cumulee = fields.Float(string="M.T cumulée", help=("Montant total réalisé jusqu'à ce jour"))
    difference1 = fields.Float(string="Différence 1", compute='_compute_differences',
                               help=("Quantité du marché - Quantité réalisée"), store=True)
    difference2 = fields.Float(string="Différence 2", compute='_compute_differences',
                               help=("Montant du marché - Montant réalisée"), store=True)
    progress_percentage = fields.Float(string="Avancement %", compute='_compute_progress', store=True,
                                       help="Pourcentage d'avancement (Quantité cumulée / Quantité marché)")
    project_id = fields.Many2one(
        "custom.project", string="Projet", required=True,
        domain="[('company_id', '=', allowed_company_ids[0])]",
    )
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user)

    qty_exceeds_marche = fields.Boolean(
        string="Dépasse la quantité du marché",
        compute='_compute_qty_exceeds_marche',
        store=False,
        help="Vrai si la quantité cumulée dépasse la quantité du marché.",
    )

    @api.depends('quantity_cumulee', 'quantity_marche')
    def _compute_qty_exceeds_marche(self):
        for rec in self:
            rec.qty_exceeds_marche = bool(
                rec.quantity_marche
                and float_compare(rec.quantity_cumulee, rec.quantity_marche, precision_digits=2) > 0
            )

    @api.onchange('quantity_cumulee', 'quantity_marche')
    def _onchange_quantity_vs_marche(self):
        if self.quantity_marche and float_compare(self.quantity_cumulee, self.quantity_marche, precision_digits=2) > 0:
            return {
                'warning': {
                    'title': _("Quantité du marché dépassée"),
                    'message': _(
                        "La quantité cumulée (%.2f) dépasse la quantité du marché (%.2f) pour l'article '%s'."
                    ) % (self.quantity_cumulee, self.quantity_marche, self.designation2 or ''),
                }
            }

    @api.depends('quantity_marche', 'quantity_cumulee')
    def _compute_progress(self):
        for rec in self:
            if rec.quantity_marche > 0:
                rec.progress_percentage = (rec.quantity_cumulee / rec.quantity_marche) * 100
            else:
                rec.progress_percentage = 0.0

    @api.depends('quantity_marche', 'quantity_cumulee', 'montant_marche', 'montant_cumulee')
    def _compute_differences(self):
        for rec in self:
            # rec.difference1 = rec.quantity_given - rec.supply_quantity
            rec.difference1 = rec.quantity_marche - rec.quantity_cumulee
            rec.difference2 = rec.montant_marche - rec.montant_cumulee


class Situation(models.Model):
    _name = "situation"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Situation des sous-traitants et des articles de stock dans le projet BTP"

    name = fields.Char("Nom de la situation", required=True)
    number = fields.Char(
        "N° Situation",
        compute='_compute_number',
        store=True,
        readonly=True,
        copy=False,
        help="Rang de la situation parmi celles du même couple (sous-traitant, projet). "
             "Format '01', '02', etc. Repart à 1 dès qu'on change de projet ou de sous-traitant."
    )
    date = fields.Date("Date de la situation", required=True)
    situation_sous_traitant_ids = fields.One2many("situation.sous.traitants", "situation_id",
                                                  string="Situation des sous-traitants")
    currency_id = fields.Many2one("res.currency", string="Devise", default=lambda self: self.env.company.currency_id)
    project_id = fields.Many2one(
        "custom.project", string="Projet", required=True,
        domain="[('company_id', '=', allowed_company_ids[0])]",
    )
    project_id1 = fields.Many2one("projects.associated", string="Projet lié", compute="_compute_project_id1",
                                  store=True)
    original_subcontractor_id = fields.Many2one('res.partner', string="Sous-traitant d'origine",
                                                domain="[('contact_type','=','SUBCONTRACTOR')]")
    situation_amount_previous = fields.Float("Montant de la situation précédente",
                                             compute="_get_previous_situation_amount", )
    situation_amount = fields.Float("Montant de la situation", compute="_compute_totals")
    situation_amount_difference = fields.Float("Différence montant situations", compute="_compute_totals")
    tva = fields.Monetary("TVA", compute="_compute_totals")
    ttc_amount = fields.Monetary("Montant TTC", compute="_compute_totals")

    net_amount = fields.Float("Montant net", compute="_compute_net_amount", store=True)
    previous_existing = fields.Boolean(string="Situation précédente existante",
                                       compute="_get_previous_situation_amount")
    total_done_amount = fields.Float("Montant total réalisé", compute="_compute_totals")
    total_R_G_C = fields.Monetary("Total RGC", compute="_get_previous_situation_amount", store=True)
    payments_count = fields.Integer("Nombre de paiements", compute='_compute_payments_count')
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user, readonly=True)
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company, required=True)
    paid_amount = fields.Float("Montant payé", readonly=True, compute='compute_amount_paid', store=True)
    amount_residual = fields.Float("Reste à payer", readonly=True, compute='compute_amount_residual', store=True)
    totalment_paye = fields.Boolean("Totalement payé", compute='compute_payments_count1', store=True)
    partiellement_paye = fields.Boolean("Partiellement payé", compute='compute_payments_count1', store=True)
    paiement_situation_ids = fields.One2many(
        'paiement.situation',
        'situation_id',
        string='Paiements'
    )
    show_payment_button = fields.Boolean(compute="_compute_show_payment_button")
    state = fields.Selection([
        ('Non_paye', 'Non payé'),
        ('Partiellement_paye', 'Partiellement payé'),
        ('Totalement_paye', 'Totalement payé'),
    ], string='État du paiement', compute='_compute_state', store=True, readonly=True, tracking=True)
    retenu_garantie = fields.Many2one("retenu.garantie", string="Retenu de garantie")
    retenu_realisation = fields.Many2one("retenu.realisation", string="Retenu de réalisation")
    lots_id = fields.Many2many('custom.task.lots', string="Lot")
    type_situation = fields.Selection([("primary", "Service"), ("secondary", "Logments")],
                                      string="Type de situation")
    guarantee_realesed = fields.Monetary(
        string="Garantie réalisation",
        compute="_compute_guarantee_realised",

        store=True,
    )
    guarantee_retained = fields.Monetary(
        string="Garantie retenue",
        compute="_get_guarantee_retained",
        store=False)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user.has_group('custom_project.group_situation_lecture_seule'):
            raise UserError(MSG_SITUATION_LECTURE_SEULE)
        # number est désormais calculé automatiquement (voir _compute_number).
        recs = super().create(vals_list)
        # Fill qty_precedente from previous situation for each created record
        for rec in recs:
            if rec.project_id and rec.original_subcontractor_id:
                last_situation = self.env['situation'].search([
                    ('project_id', '=', rec.project_id.id),
                    ('original_subcontractor_id', '=', rec.original_subcontractor_id.id),
                    ('id', '!=', rec.id),
                ], order='date desc, id desc', limit=1)
                if last_situation:
                    for line in rec.situation_sous_traitant_ids:
                        matched = last_situation.situation_sous_traitant_ids.filtered(
                            lambda l, desig=line.designation: l.designation == desig
                        )
                        if matched and not line.qty_precedente:
                            line.qty_precedente = matched[0].qty_cummulee or 0.0
        return recs

    def write(self, vals):
        if self.env.user.has_group('custom_project.group_situation_lecture_seule'):
            raise UserError(MSG_SITUATION_LECTURE_SEULE)
        return super().write(vals)

    def unlink(self):
        if self.env.user.has_group('custom_project.group_situation_lecture_seule'):
            raise UserError(MSG_SITUATION_LECTURE_SEULE)
        return super().unlink()

    @api.depends('ttc_amount', 'retenu_garantie')
    def _get_guarantee_retained(self):
        for rec in self:
            rec.guarantee_retained = (rec.ttc_amount or 0.0) * (rec.retenu_garantie.name or 0.0) / 100

    @api.depends('ttc_amount', 'retenu_realisation')
    def _compute_guarantee_realised(self):
        for rec in self:
            rec.guarantee_realesed = (rec.ttc_amount or 0.0) * (rec.retenu_realisation.name or 0.0) / 100

    @api.depends('ttc_amount', 'guarantee_realesed', 'guarantee_retained')
    def _compute_net_amount(self):
        for rec in self:
            rec.net_amount = rec.ttc_amount - (rec.guarantee_realesed + rec.guarantee_retained)

    @api.onchange('type_situation', 'project_id')
    def _onchange_type_situation(self):
        """
        Rebuild lots and sous-traitant lines each time type_situation or project changes.
        Show ONLY lots related to the found 'projects.associated' (assoc).
        Defensive: detect where lots are stored on assoc or inside task lines.
        """
        self.ensure_one()
        try:
            # clear current selections (we rebuild everything)
            self.lots_id = [(5, 0, 0)]
            self.situation_sous_traitant_ids = [(5, 0, 0)]

            # if missing required context, return empty domains
            if not self.project_id or not self.original_subcontractor_id:
                return {'domain': {'lots_id': [], 'situation_sous_traitant_ids.task_id': []}}

            # find associated record
            assoc = self.env['projects.associated'].search([
                ('project_id', '=', self.project_id.id),
                ('original_subcontractor_id', '=', self.original_subcontractor_id.id),
            ], limit=1)

            if not assoc:
                return {'domain': {'lots_id': [], 'situation_sous_traitant_ids.task_id': []}}

            # --- Determine lots related to assoc (multiple strategies) ---
            lots_ids = []

            # Strategy 1: assoc has a direct relation field named 'lot_ids' (many2many or one2many)
            if 'lot_ids' in assoc._fields:
                lots_ids = assoc.lot_ids.ids

            # Strategy 2: assoc has field with another likely name like 'lots_id' or 'custom_task_lot_ids'
            if not lots_ids:
                for cand in ('lots_id', 'custom_task_lot_ids', 'task_lots', 'lot_ids'):
                    if cand in assoc._fields:
                        lots_ids = getattr(assoc, cand).ids
                        if lots_ids:
                            break

            # Strategy 3: gather lots from assoc.task_line_ids (try several possible fields)
            if not lots_ids and 'task_line_ids' in assoc._fields:
                for tl in assoc.task_line_ids:
                    # common patterns: tl.lot_id OR tl.task_id.lot_id
                    lot = getattr(tl, 'lot_id', False)
                    if lot:
                        lots_ids.append(lot.id)
                        continue
                    task = getattr(tl, 'task_id', False)
                    if task:
                        lot2 = getattr(task, 'lot_id', False)
                        if lot2:
                            lots_ids.append(lot2.id)
                            continue
                    # sometimes the task_line directly references a custom.task.lots via field 'custom_lot_id'
                    for cand in ('custom_lot_id', 'lot', 'lot_id'):
                        if cand in tl._fields:
                            lv = getattr(tl, cand, False)
                            if lv:
                                lots_ids.append(lv.id)

            # unique and filter out falsy
            lots_ids = list({int(x) for x in lots_ids if x})

            # If type_situation set, further filter lots by import_source (defensive)
            if self.type_situation and lots_ids:
                filtered = self.env['custom.task.lots'].search([
                    ('id', 'in', lots_ids),
                    ('import_source', '=', self.type_situation)
                ])
                lots_ids = filtered.ids

            # Apply lots to the record (if any)
            if lots_ids:
                self.lots_id = [(6, 0, lots_ids)]
                domain_lots = [('id', 'in', lots_ids)]
            else:
                domain_lots = [('id', '=', False)]  # no lots to show

            # --- detect if child model has 'task_id' many2one (prevent ValueError) ---
            child_model = self.env['situation.sous.traitants']
            has_task_field = 'task_id' in child_model._fields

            # --- rebuild sous-traitant lines from assoc.task_line_ids ---
            task_lines = []
            # For building lines we reuse assoc.task_line_ids if present
            if 'task_line_ids' in assoc._fields:
                for al in assoc.task_line_ids:
                    # skip lines that don't match the selected type (if type_situation set)
                    if self.type_situation and getattr(al, 'task_id_import_source',
                                                       False) and al.task_id_import_source != self.type_situation:
                        continue

                    line_vals = {
                        'num': getattr(al.task_id, 'no', False),
                        'designation': getattr(al.task_id, 'name', False),
                        'unit': (al.task_id.unit.id if getattr(al, 'task_id', False) and getattr(al.task_id, 'unit',
                                                                                                 False) else False),
                        'qty_marche': getattr(al, 'quantity', 0.0),
                        'prix_unitaire_convention': getattr(al, 'unit_price', 0.0),
                        'type_tasks': getattr(al, 'task_id_import_source', False),
                    }

                    # only include task_id if the child model actually defines it
                    if has_task_field and getattr(al, 'task_id', False):
                        line_vals['task_id'] = al.task_id.id

                    task_lines.append((0, 0, line_vals))

            # assign built lines (safe because we only use fields that exist)
            if task_lines:
                self.situation_sous_traitant_ids = task_lines
            else:
                # if no lines found, keep it empty
                self.situation_sous_traitant_ids = [(5, 0, 0)]

            # Fill qty_precedente from the previous situation
            self._fill_qty_precedente_from_previous()

            # prepare domain for inner task field only if exists
            domain_task = []
            if has_task_field and self.type_situation:
                domain_task = [('import_source', '=', self.type_situation)]

            return {
                'domain': {
                    'lots_id': domain_lots,
                    **({'situation_sous_traitant_ids.task_id': domain_task} if has_task_field else {}),
                }
            }

        except Exception as e:
            _logger.exception("Error in _onchange_type_situation: %s", e)
            # return empty domains on error to avoid client crash
            return {'domain': {'lots_id': [], 'situation_sous_traitant_ids.task_id': []}}

    def _fill_qty_precedente_from_previous(self):
        """Fill qty_precedente on current lines from the last situation for the same project/subcontractor."""
        self.ensure_one()
        if not self.project_id or not self.original_subcontractor_id:
            return
        domain = [
            ('project_id', '=', self.project_id.id),
            ('original_subcontractor_id', '=', self.original_subcontractor_id.id),
        ]
        if self.id:
            domain.append(('id', '!=', self.id))
        last_situation = self.env['situation'].search(domain, order='date desc', limit=1)
        if not last_situation:
            return
        for line in self.situation_sous_traitant_ids:
            matched = last_situation.situation_sous_traitant_ids.filtered(
                lambda l: l.designation == line.designation
            )
            if matched:
                line.qty_precedente = matched[0].qty_cummulee or 0.0

    # compute project_id1 based on project_id and original_subcontractor_id
    @api.depends('project_id', 'original_subcontractor_id')
    def _compute_project_id1(self):
        for rec in self:
            assoc = self.env['projects.associated'].search([
                ('project_id', '=', rec.project_id.id),
                ('original_subcontractor_id', '=', rec.original_subcontractor_id.id),
            ], limit=1)
            rec.project_id1 = assoc.id if assoc else False

    @api.depends('totalment_paye', 'partiellement_paye')
    def _compute_state(self):
        for rec in self:
            if rec.totalment_paye:
                rec.state = 'Totalement_paye'
            elif rec.partiellement_paye:
                rec.state = 'Partiellement_paye'
            else:
                rec.state = 'Non_paye'

    @api.onchange('date')
    def _onchange_date_fill_last_done_quantity(self):

        # if not self.designation or not self.situation_id:
        #     return
        #
        # # bloqué la creation d'un article deux fois
        # duplicates = self.situation_id.situation_sous_traitant_ids.filtered(
        #     lambda l: l.designation == self.designation and l != self and l.situation_id == self.situation_id
        # )
        #
        # if duplicates:
        #     raise UserError(_("L'article %s est déjà ajouté à cette situation.") % self.article.name)

        # Remplir done_quantity_current avec la dernière situation enregistrée pour le même article
        for rec in self:
            project = rec.project_id
            subcontractor = rec.original_subcontractor_id

            # إذا لا مشروع أو لا مقاول أصلي فلا نفعل شيء
            if not project or not subcontractor:
                # تصفير للخطوط الحالية إن رغبت
                for line in rec.situation_sous_traitant_ids:
                    line.qty_precedente = 0.0
                continue

            domain = [
                ('project_id', '=', project.id),
                ('original_subcontractor_id', '=', subcontractor.id),
            ]

            # استبعد الوضع الحالي اذا كان مسجلاً
            if rec.id:
                domain.append(('id', '!=', rec.id))

            last_situation = self.env['situation'].search(domain, order='date desc', limit=1)

            if not last_situation:
                # لم توجد حالة سابقة: نضع صفر لكل الخطوط
                for line in rec.situation_sous_traitant_ids:
                    line.qty_precedente = 0.0
                continue

            # وجدنا last_situation (سجل واحد) — الآن تعامل مع خطوطه بعناية
            for line in rec.situation_sous_traitant_ids:
                # فلترة خطوط الـ last_situation بحسب الـ designation المطابق
                matched_lines = last_situation.situation_sous_traitant_ids.filtered(
                    lambda l: l.designation == line.designation
                )
                if not matched_lines:
                    # Tâche inexistante dans la situation précédente = 0
                    line.qty_precedente = 0.0
                else:
                    # Utiliser la quantité cumulée de la situation précédente
                    last_line = matched_lines[0]
                    line.qty_precedente = last_line.qty_cummulee or 0.0

    def _compute_show_payment_button(self):
        for rec in self:
            rec.show_payment_button = not self.env.user.has_group('custom_groups.group_technique')

    @api.depends('amount_residual', 'paid_amount', 'net_amount')
    def compute_payments_count1(self):
        for rec in self:
            rec.totalment_paye = False
            rec.partiellement_paye = False

            if rec.net_amount <= 0:
                # Pas encore de montant défini → non payé
                continue

            if rec.paid_amount == 0:
                # Rien payé → non payé
                continue

            if rec.paid_amount >= rec.net_amount:
                # Tout payé → totalement payé
                rec.totalment_paye = True
            elif 0 < rec.paid_amount < rec.net_amount:
                # Partiellement payé
                rec.partiellement_paye = True

    @api.depends('paiement_situation_ids.amount_paid', 'paiement_situation_ids.status')
    def compute_amount_paid(self):
        for rec in self:
            paid = sum(
                rec.paiement_situation_ids.filtered(lambda p: p.status == 'paid').mapped('amount_paid')
            )
            rec.paid_amount = paid

    @api.depends('net_amount', 'paid_amount')
    def compute_amount_residual(self):
        for rec in self:
            rec.amount_residual = rec.net_amount - rec.paid_amount

    def _compute_payments_count(self):
        for rec in self:
            payments = self.env['paiement.situation'].search([('situation_id', '=', rec.id)])
            rec.payments_count = len(payments)

    def _get_previous_situation_amount(self):
        for rec in self:
            previous_situation = self.env['situation'].search([
                ('project_id', '=', rec.project_id.id),
                ('original_subcontractor_id', '=', rec.original_subcontractor_id.id),
                ('create_date', '<', rec.create_date)
            ], order='date desc', limit=1)
            rec.previous_existing = bool(previous_situation)
            rec.situation_amount_previous = previous_situation.total_done_amount if previous_situation else 0.0
            previous_situations = self.env['situation'].search([('project_id', '=', rec.project_id.id),
                                                                ('original_subcontractor_id', '=',
                                                                 rec.original_subcontractor_id.id),
                                                                ('create_date', '<=', rec.create_date)
                                                                ], order='date desc')
            rec.total_R_G_C = sum(rec.guarantee_retained for rec in previous_situations)

    @api.depends('situation_sous_traitant_ids.montant_mois',
                 'project_id.tax_ids.amount')
    def _compute_totals(self):
        for rec in self:
            rec.total_done_amount = sum(
                sous_traitant.montant_mois for sous_traitant in rec.situation_sous_traitant_ids)
            rec.situation_amount_difference = rec.total_done_amount - rec.situation_amount_previous
            rec.situation_amount = rec.total_done_amount
            rec.tva = rec.situation_amount * rec.project_id1.tax_ids.amount  # Assuming a fixed TVA rate of 19%
            rec.ttc_amount = rec.situation_amount + rec.tva

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)

        project_id = self.env.context.get('default_project_id')
        subcontractor_id = self.env.context.get('default_original_subcontractor_id')

        if project_id and subcontractor_id:
            assoc = self.env['projects.associated'].search([
                ('project_id', '=', project_id),
                ('original_subcontractor_id', '=', subcontractor_id),
            ], limit=1)
            if assoc:
                # Find the previous situation to fill qty_precedente
                last_situation = self.env['situation'].search([
                    ('project_id', '=', project_id),
                    ('original_subcontractor_id', '=', subcontractor_id),
                ], order='date desc', limit=1)

                task_lines = []
                for line in assoc.task_line_ids:
                    qty_prec = 0.0
                    if last_situation:
                        matched = last_situation.situation_sous_traitant_ids.filtered(
                            lambda l, name=line.task_id.name: l.designation == name
                        )
                        if matched:
                            qty_prec = matched[0].qty_cummulee or 0.0

                    task_lines.append((0, 0, {
                        'num': line.task_id.no,
                        'designation': line.task_id.name,
                        'unit': line.task_id.unit.id,
                        'qty_marche': line.quantity,
                        'qty_precedente': qty_prec,
                        'prix_unitaire_convention': line.unit_price,
                        'type_tasks': line.task_id_import_source,
                    }))

                defaults['situation_sous_traitant_ids'] = task_lines

        return defaults

    def open_wizard_payment_situation(self):
        self.ensure_one()
        if self.net_amount == self.paid_amount and self.net_amount > 0:
            raise UserError("la situation est totalement payée, vous ne pouvez pas effectuer un nouveau paiement.")
        return {
            'name': 'Paiement de la situation',
            'type': 'ir.actions.act_window',
            'res_model': 'paiement.situation',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_situation_id': self.id,
                'default_reference': f'Paiement-{self.name}',
                'default_partner_id': self.original_subcontractor_id.id,
                'default_project_id': self.project_id.id,
                'default_amount_paid': self.amount_residual,
                'default_payment_method_id': self.env.ref('custom_project.account_payment_method_espece_out').id,
            }
        }

    def action_open_view_paeiment_situation(self):
        self.ensure_one()
        return {
            'name': 'Paiements des situations',
            'type': 'ir.actions.act_window',
            'res_model': 'paiement.situation',
            'view_mode': 'tree,form',
            'domain': [('situation_id', '=', self.id)],
        }

    def poush_notification(self):
        self.ensure_one()
        print("\n✅ poush_notification() appelée pour :", self.name)

        # 1) Auteur = PARTNER tiers (OdooBot si dispo, sinon Admin partner)
        author_partner = self.env.ref('mail_bot.partner_odoo_bot', raise_if_not_found=False) \
                         or self.env.ref('base.partner_root')
        author_partner_id = author_partner.id

        # 2) Cibles = Farhi + Mesrane (partners)
        target_users = self.env['res.users'].sudo().search([
            '|',
            ('name', 'ilike', 'Farhi Souhila'),
            ('name', 'ilike', 'Mesrane Sabrina'),
        ])
        if not target_users:
            raise UserError("Aucun des managers (Farhi Souhila, Mesrane Sabrina) n'a pas ete trouve.")
        partner_ids = target_users.mapped('partner_id').ids

        # 3) Lien vers la situation
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        # Récupérer le dernier paiement lié à la situation
        last_paiement = self.paiement_situation_ids.sorted(lambda p: p.create_date)[
            -1] if self.paiement_situation_ids else False
        domain = [
            ('situation_id', '=', self.id),
            ('state', '!=', 'done')
        ]
        versement_associated = self.env['versement.subcontractor'].search(
            domain,
            order='create_date desc',
            limit=1
        )
        print("🔗 versement_associated trouvé :", versement_associated)
        # Générer l'URL du dernier paiement
        situation_url = ''
        if versement_associated:
            situation_url = f"{base_url}/web#id={versement_associated.id}&model=versement.subcontractor&view_type=form"

        # 4) Contenu HTML (➡️ rend le lien cliquable)
        html_content = f"""
            <p><b>Bonjour,</b></p>
            <p>Vous avez une nouvelle demande de versement à valider.</p>
            <p>👉 <a href="{situation_url}" target="_blank" rel="noopener">
                Ouvrir le versement de la situation {self.name or ''}
            </a></p>
            <p>— L'équipe {self.company_id.name or ''}</p>
        """

        # 5) Canal (v17 = discuss.channel)
        Channel = self.env['discuss.channel']
        channel = Channel.sudo().search([('name', '=', 'Paiements à valider')], limit=1)
        if not channel:
            channel = Channel.sudo().create({
                'name': 'Paiements à valider',
                'description': 'Notifications des paiements à valider',
            })
        # 6) Ajouter Farhi et Mesrane au canal
        for pid in partner_ids:
            if 'members' in channel._fields and pid not in channel.sudo().members.ids:
                channel.sudo().write({'members': [(4, pid)]})

        # 7) Poster (HTML + pas de notification_ids en v17)
        mt_comment = self.env.ref('mail.mt_comment', raise_if_not_found=False)
        channel.sudo().message_post(
            author_id=author_partner_id,
            body=html_content,
            body_is_html=True,
            message_type='comment',
            partner_ids=partner_ids,
            subtype_id=mt_comment.id if mt_comment else False,
        )
        return True

    def get_subcontractor_situation_number(self):
        """Compatibilité rapport : retourne le n° calculé (champ 'number')."""
        self.ensure_one()
        return self.number or 'SIT/0001'

    @api.depends('original_subcontractor_id', 'project_id', 'date')
    def _compute_number(self):
        """N° Situation = rang dans le couple (sous-traitant, projet)
        trié par (date, id), format 'SIT/0001'..."""
        # Recalcul ciblé pour la situation courante
        for sit in self:
            if not sit.original_subcontractor_id or not sit.project_id or not sit.date:
                sit.number = 'SIT/0001'
                continue
            domain = [
                ('original_subcontractor_id', '=', sit.original_subcontractor_id.id),
                ('project_id', '=', sit.project_id.id),
                ('date', '<=', sit.date),
            ]
            # Si record déjà sauvegardé, on l'exclut via id < self.id ;
            # sinon (NewId en mémoire), on ne filtre pas sur l'id.
            if isinstance(sit.id, int):
                domain.append(('id', '<', sit.id))
            previous_count = self.search_count(domain)
            sit.number = 'SIT/%04d' % (previous_count + 1)

        # Re-déclenche le recalcul des autres situations sauvegardées des mêmes
        # couples touchés (au cas où l'insertion change leur position).
        saved_ids = [s.id for s in self if isinstance(s.id, int)]
        couples = {(s.original_subcontractor_id.id, s.project_id.id) for s in self
                   if s.original_subcontractor_id and s.project_id}
        for st_id, p_id in couples:
            siblings = self.search([
                ('original_subcontractor_id', '=', st_id),
                ('project_id', '=', p_id),
                ('id', 'not in', saved_ids),
            ])
            for sib in siblings:
                if not sib.date:
                    sib.number = 'SIT/0001'
                    continue
                previous_count = self.search_count([
                    ('original_subcontractor_id', '=', st_id),
                    ('project_id', '=', p_id),
                    ('date', '<=', sib.date),
                    ('id', '<', sib.id),
                ])
                sib.number = 'SIT/%04d' % (previous_count + 1)

    def write(self, vals):
        res = super().write(vals)
        if 'situation_sous_traitant_ids' in vals:
            self._recompute_line_nums()
        return res

    def _recompute_line_nums(self):
        """Réassigne les numéros existants selon le nouvel ordre de séquence"""
        for situation in self:
            lines = situation.situation_sous_traitant_ids.sorted('sequence')
            # Collecter les numéros existants triés
            nums = sorted(lines.mapped('num'), key=lambda n: n or '')
            for line, new_num in zip(lines, nums):
                if line.num != new_num:
                    line.write({'num': new_num})

    def amount_to_words(self):
        """Convertir le montant net en lettres (français)"""
        self.ensure_one()
        try:
            from num2words import num2words
            amount = self.net_amount
            integer_part = int(amount)
            decimal_part = round((amount - integer_part) * 100)
            result = num2words(integer_part, lang='fr')
            result += " dinars et %s centimes" % num2words(decimal_part, lang='fr')
            return result.upper()
        except ImportError:
            return "%.2f DA" % self.net_amount

    def action_preview_report(self):
        """Prévisualiser le rapport dans un nouvel onglet"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/custom_project.report_situation_document/%s' % self.id,
            'target': 'new',
        }
