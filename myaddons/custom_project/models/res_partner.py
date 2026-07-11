import logging
import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ProjectsAssociated(models.Model):
    _name = 'projects.associated'
    _description = 'Projects Associated'
    _rec_name = 'project_id'

    @api.constrains('lots_id')
    def _check_lots_limit(self):
        """Constraint: If company is NOT 'SARL IMMOBILIERE INNOVATION', sous-traitants can only select 1 lot"""
        for rec in self:
            if rec.company_id and rec.company_id.name != 'SARL IMMOBILIERE INNOVATION':
                if len(rec.lots_id) > 1:
                    raise UserError(_(
                        "Vous ne pouvez sélectionner qu'un seul lot par projet. "
                        "Veuillez contacter l'administrateur pour plus d'informations."
                    ))

    project_id = fields.Many2one('custom.project', string="Project",
                                  domain="[('company_id', '=', allowed_company_ids[0])]")
    client_id = fields.Many2one(related='project_id.client_id', string="Client", store=True)
    state = fields.Selection(related='project_id.state', string="State", store=True)
    task_line_ids = fields.One2many('partner.task.line', 'project_id', string="Cahier de charges")
    tax_totale = fields.Float("Total", compute="_compute_tax_totale", store=True)
    total_price = fields.Float(string="Total HT", compute="_compute_total_price", store=True)
    total = fields.Float("Total TTC", compute="_compute_total", store=True)
    currency_id = fields.Many2one("res.currency", string="Devise", default=lambda self: self.env.company.currency_id)
    original_subcontractor_id = fields.Many2one('res.partner', string="Sous-traitant d'origine",
                                                domain="[('contact_type','=','SUBCONTRACTOR')]")
    tax_ids = fields.Many2one(
        'account.tax',
        string="Taxes",


    )
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    lots_id = fields.Many2many('custom.task.lots', string="Lot",
                               help="Lot associé aux tâches du projet",
                               domain="[('project_id', '=', project_id)]")
    is_etb_tph_chellil = fields.Boolean(
        string="Is ETB TPH CHellil",
        compute='_compute_company_flags',
        store=False,  # set True if you need to search/sort on this field
    )
    previous_existing = fields.Boolean(string="Situation précédente existante",
                                       )
    retenu_garantie = fields.Many2one("retenu.garantie", string="Retenu de garantie")
    retenu_realisation = fields.Many2one("retenu.realisation", string="Retenu de réalisation")

    guarantee_retained = fields.Monetary(
        string="Garantie retenue",
        compute="_compute_guarantee_retained",
        currency_field='currency_id',
        store=True,
    )
    guarantee_realesed = fields.Monetary(
        string="Garantie réalisation",
        compute="_compute_guarantee_realised",
        currency_field='currency_id',
        store=True,
    )
    net_amount = fields.Float("Montant net", compute="_compute_net_a_payer")


    @api.depends('retenu_garantie', 'total')
    def _compute_guarantee_retained(self):
        for rec in self:
            rec.guarantee_retained = (rec.total or 0.0) * (rec.retenu_garantie.name or 0.0) / 100

    @api.depends('retenu_realisation', 'total')
    def _compute_guarantee_realised(self):
        for rec in self:
            rec.guarantee_realesed = (rec.total or 0.0) * (rec.retenu_realisation.name or 0.0) / 100

    @api.depends('guarantee_realesed', 'guarantee_retained', 'total')
    def _compute_net_a_payer(self):
        for rec in self:
            rec.net_amount = rec.total - (rec.guarantee_retained + rec.guarantee_realesed )


    @api.depends('company_id', 'original_subcontractor_id', 'original_subcontractor_id.company_id')
    def _compute_company_flags(self):
        """Compute company-specific flags safely for every record."""
        special_name = "ETB TPH CHellil"
        for rec in self:
            try:
                # default value for every record (important!)
                rec.is_etb_tph_chellil = False

                # 1) Prefer subcontractor's company when available
                subco = getattr(rec.original_subcontractor_id, 'company_id', False)
                if subco and getattr(subco, 'name', False) and subco.name.strip() == special_name:
                    rec.is_etb_tph_chellil = True
                    continue

                # 2) Then check the record's company (company_id)
                if rec.company_id and getattr(rec.company_id, 'name',
                                              False) and rec.company_id.name.strip() == special_name:
                    rec.is_etb_tph_chellil = True
                    continue


            except Exception as e:
                _logger.exception("Error computing is_etb_tph_chellil for projects.associated id=%s: %s", rec.id, e)
                # ensure we still assign a value
                try:
                    rec.is_etb_tph_chellil = False
                except Exception:
                    _logger.error("Failed to assign default is_etb_tph_chellil for id=%s", rec.id)

    @api.onchange('project_id')
    def _onchange_project_id(self):
        for rec in self:
            # interdire la creation dun projet deux fois pour le même partenaire
            if not rec.project_id:
                continue
            existing = self.env['projects.associated'].search([
                ('project_id', '=', rec.project_id.id),
                ('original_subcontractor_id', '=', rec.original_subcontractor_id.id),
            ])
            if existing:
                raise UserError("Ce projet est déjà associé à ce sous-traitant.")

    # 1) compute total_price = sum des lignes
    @api.depends('task_line_ids.total_price')
    def _compute_total_price(self):
        for rec in self:
            rec.total_price = sum(line.total_price for line in rec.task_line_ids)

    # 2) compute tax_totale en fonction du total_price et des taxes
    @api.depends('total_price', 'tax_ids')
    def _compute_tax_totale(self):
        for rec in self:
            total_tax = 0.0
            # si plusieurs taxes, on les additionne (exemple simple pour taux en %)
            for tax in rec.tax_ids:
                total_tax += (rec.total_price * (tax.amount or 0.0)) / 100.0
            rec.tax_totale = total_tax

    # 3) compute final TTC
    @api.depends('total_price', 'tax_totale')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.total_price + rec.tax_totale

    def _get_qty_allocated_to_other_subs(self, task):
        """Retourne la somme des `quantity` déjà allouées à cette tâche
        pour ce projet, dans des conventions OTHER que la convention courante
        (utile pour multi-sous-traitants sur la même tâche)."""
        self.ensure_one()
        if not task or not self.project_id:
            return 0.0
        domain = [
            ('task_id', '=', task.id),
            ('project_id.project_id', '=', self.project_id.id),
        ]
        if self._origin and self._origin.id:
            domain.append(('project_id', '!=', self._origin.id))
        return sum(self.env['partner.task.line'].search(domain).mapped('quantity') or [0.0])

    # onchange lots -> ajoute récursivement parents + descendants
    @api.onchange('lots_id')
    def _onchange_lots_id(self):
        for rec in self:
            if not rec.lots_id or not rec.lots_id.task_ids:
                rec.task_line_ids = [(5, 0, 0)]
                continue

            rec.task_line_ids = [(5, 0, 0)]
            task_lines = []
            seen = set()

            def walk(task, level=0):
                if not task or task.id in seen:
                    return

                seen.add(task.id)
                marche_qty = task.quantity or 0.0
                # Convention par défaut = quantité projet - déjà alloué à d'autres
                # sous-traitants pour cette même tâche dans ce projet
                allocated_to_others = rec._get_qty_allocated_to_other_subs(task)
                default_qty = max(marche_qty - allocated_to_others, 0.0)

                task_lines.append((0, 0, {
                    'no': task.no,
                    'task_id': task.id,
                    'description': task.name,
                    'quantity_marche': marche_qty,
                    'quantity': default_qty,
                    'unit_price': task.unit_price or 0.0,
                    'unit': task.unit.id if task.unit else False,
                }))

                # تحقق من وجود الحقل 'sequence' بطريقة آمنة
                if 'sequence' in task.child_ids._fields:
                    children = task.child_ids.sorted('sequence')
                else:
                    children = task.child_ids

                for ch in children:
                    walk(ch, level + 1)

            top_tasks = rec.lots_id.task_ids.filtered(lambda t: not t.parent_id)
            # تحقق من وجود الحقل 'sequence' على مستوى الـ recordset
            if 'sequence' in top_tasks._fields:
                top_tasks = top_tasks.sorted('sequence')
            for t in top_tasks:
                walk(t, level=0)

            rec.task_line_ids = task_lines

    @api.onchange('task_line_ids')
    def _check_quantity(self):
        """Avertit en temps réel : doublon de tâche, ou somme des quantités
        (toutes conventions du projet) dépassant la quantité du projet."""
        self.ensure_one()
        real_id = self._origin.id if isinstance(self._origin.id, int) else False
        seen_tasks = set()
        for line in self.task_line_ids:
            if not line.task_id:
                continue

            if line.task_id.id in seen_tasks:
                return {
                    'warning': {
                        'title': _("Doublon de tâche"),
                        'message': _("La tâche '%s' est sélectionnée plusieurs fois.") % (line.task_id.name or ''),
                    }
                }
            seen_tasks.add(line.task_id.id)

            db_domain = [
                ('task_id', '=', line.task_id.id),
                ('project_id', '!=', False),
            ]
            if real_id:
                db_domain.append(('project_id', '!=', real_id))
            existing_db_qty = sum(self.env['partner.task.line'].search(db_domain).mapped('quantity') or [])
            qty_in_rec = sum(self.task_line_ids.filtered(lambda l: l.task_id == line.task_id).mapped('quantity'))
            total_selected_qty = existing_db_qty + qty_in_rec

            if total_selected_qty > (line.task_id.quantity or 0.0):
                return {
                    'warning': {
                        'title': _("Quantité du projet dépassée"),
                        'message': _(
                            "La quantité totale allouée (%.2f) pour la tâche '%s' dépasse la quantité du projet (%.2f)."
                        ) % (total_selected_qty, line.task_id.name or '', line.task_id.quantity or 0.0),
                    }
                }

    # 'import_source': task_line.task_id.import_source,
    def _build_task_vals_from_original(self, original_task, task_line, lot_mapping):
        """بناء قيم المهمة الجديدة بالاستناد للمهمة الأصلية + تعديل من task_line (إذا موجود)."""
        vals = {
            'project_id': False,  # ستُملأ لاحقًا من قبل المُستدعي (new_project.id)
            'no': original_task.no or (task_line.no if task_line else 'N/A'),
            'name': (task_line.description or original_task.name) or f"Task {original_task.id}",
            'quantity': (task_line.quantity if task_line and task_line.quantity is not None else (
                    original_task.quantity or 0.0)),
            'unit_price': (task_line.unit_price if task_line and task_line.unit_price is not None else (
                    original_task.unit_price or 0.0)),
        }
        if hasattr(original_task, 'tax_ids') and original_task.tax_ids:
            vals['tax_ids'] = [(6, 0, original_task.tax_ids.ids)]
        elif primary_taxes:  # Use project-level taxes as fallback
            vals['tax_ids'] = primary_taxes
        # وحدات، لوت، import_source، flags (is_title, is_category) إن وجدت
        if original_task.unit:
            vals['unit'] = original_task.unit.id
        if task_line and task_line.lot_id and task_line.lot_id.id in lot_mapping:
            vals['lot_id'] = lot_mapping[task_line.lot_id.id]
        elif getattr(original_task, 'lot_id', False) and original_task.lot_id.id in lot_mapping:
            vals['lot_id'] = lot_mapping[original_task.lot_id.id]
        if hasattr(original_task, 'import_source'):
            vals['import_source'] = original_task.import_source
        if hasattr(original_task, 'is_title') and original_task.is_title:
            vals['is_title'] = True
        if hasattr(original_task, 'is_category') and original_task.is_category:
            vals['is_category'] = True
        # sequence إذا وجد
        if 'sequence' in original_task._fields and getattr(original_task, 'sequence', False):
            vals['sequence'] = original_task.sequence
        tax_ids_to_apply = []

        # 1) taxes on the task_line (if such field exists)
        if task_line and hasattr(task_line, 'tax_ids') and task_line.tax_ids:
            tax_ids_to_apply = task_line.tax_ids.ids

        # 2) else taxes on original_task (if exists)
        if not tax_ids_to_apply and hasattr(original_task, 'tax_ids') and original_task.tax_ids:
            tax_ids_to_apply = original_task.tax_ids.ids

        # 3) else taxes on the lot (if present and in mapping)
        if not tax_ids_to_apply:
            lot_obj = None
            # choose task_line.lot_id or original_task.lot_id
            if task_line and getattr(task_line, 'lot_id', False):
                lot_obj = task_line.lot_id
            elif getattr(original_task, 'lot_id', False):
                lot_obj = original_task.lot_id
            if lot_obj and hasattr(lot_obj, 'tax_ids') and lot_obj.tax_ids:
                tax_ids_to_apply = lot_obj.tax_ids.ids

        # 4) else taxes set on the projects.associated record (self.tax_ids)
        if not tax_ids_to_apply and hasattr(self, 'tax_ids') and self.tax_ids:
            tax_ids_to_apply = self.tax_ids.ids

        # 5) fallback: search a default tax (e.g. 19%)
        if not tax_ids_to_apply:
            default_tax = self.env['account.tax'].search([('amount', '=', 19.0)], limit=1)
            if default_tax:
                tax_ids_to_apply = default_tax.ids

        # apply tax_ids if found (Many2many for create: (6, 0, ids) )
        if tax_ids_to_apply:
            vals['tax_ids'] = [(6, 0, tax_ids_to_apply)]

        return vals

    def create_custom_project(self):
        self.ensure_one()

        # validations initiales
        if not self.project_id:
            raise UserError("يجب اختيار مشروع أساسي أولاً")
        if not self.task_line_ids:
            raise UserError("لا توجد مهام لإنشاء المشروع الجديد")

        # determine company
        default_company = self.env.company
        subcontractor_company = (
            self.original_subcontractor_id.company_id if self.original_subcontractor_id and self.original_subcontractor_id.company_id else None)

        # 2) نبحث عن شركة فرعية باسم محدد داخل هرم الشركات للشركة الافتراضية
        special_company = False
        special_name = "ETB TPH CHellil"
        # نبحث داخل companies المتاحة (global) لتجنب مشاكل child_ids غير متوقعة
        special_company = self.env['res.company'].search([('name', '=', special_name)], limit=1)

        # 3) قرار نهائي: أولوية: subcontractor_company إذا اسمها يطابق special_name
        if subcontractor_company and subcontractor_company.name == special_name:
            target_company = subcontractor_company
        elif special_company:
            # إذا وجدنا شركة بإسم الخاص نستخدمها
            target_company = special_company
        else:
            # إلا فالنستخدم الشركة الافتراضية (env.company)
            target_company = default_company

        # الآن company_id كرقم
        company_id_int = target_company.id if target_company else default_company.id

        def _get_or_create_tax(amount, company_id, tax_type='sale'):
            """Get or create tax with specified amount"""
            tax = self.env['account.tax'].search([
                ('company_id', '=', company_id),
                ('amount', '=', float(amount)),
                ('type_tax_use', '=', tax_type)
            ], limit=1)

            if not tax:
                tax = self.env['account.tax'].create({
                    'name': f'TVA {amount}%',
                    'amount': float(amount),
                    'amount_type': 'percent',
                    'type_tax_use': tax_type,
                    'company_id': company_id,
                })
            return tax

        # Determine which taxes to use
        primary_taxes = []
        secondary_taxes = []

        # Option 1: Use taxes from the current record
        if self.tax_ids:
            primary_taxes = [(6, 0, self.tax_ids.ids)]
        else:
            # Option 2: Use default 19% tax
            default_tax = _get_or_create_tax(19.0, company_id_int)
            primary_taxes = [(6, 0, [default_tax.id])]

        # Option 3: Copy taxes from original project
        if hasattr(self.project_id, 'tax_ids') and self.project_id.tax_ids and not primary_taxes:
            primary_taxes = [(6, 0, self.project_id.tax_ids.ids)]

        # Handle secondary taxes for logments (9%)
        if hasattr(self.project_id, 'tax_ids_2') and self.project_id.tax_ids_2:
            secondary_taxes = [(6, 0, self.project_id.tax_ids_2.ids)]
        else:
            # Create default 9% tax if needed
            default_tax_9 = _get_or_create_tax(9.0, company_id_int)
            secondary_taxes = [(6, 0, [default_tax_9.id])]

        # Create new project with TVA
        new_project_vals = {
            'name': f"{self.project_id.name} - {self.original_subcontractor_id.name if self.original_subcontractor_id else 'No Sub'}",
            'client_id': self.client_id.id,
            'state': 'draft',
            'is_internal': getattr(self.project_id, 'is_internal', False),
            'company_id': company_id_int,
            'tax_ids': primary_taxes,  # Primary taxes (19%)
        }

        # Add secondary taxes if the model supports it
        if hasattr(self.env['custom.project'], 'tax_ids_2'):
            new_project_vals['tax_ids_2'] = secondary_taxes  # Secondary taxes (9%)

        new_project = self.env['custom.project'].create(new_project_vals)

        # -------------------------
        # Create lots and build lot_mapping (old_lot_id -> new_lot_id)
        # -------------------------
        lot_mapping = {}
        needed_lots = self.task_line_ids.mapped('lot_id').filtered(lambda l: l)

        lot_model = self.env['custom.task.lots']
        has_lot_sequence_field = 'sequence' in lot_model._fields

        if has_lot_sequence_field:
            needed_lots = needed_lots.sorted('sequence')
        else:
            needed_lots = needed_lots.sorted('name')

        for lot in needed_lots:
            try:
                new_lot = self.env['custom.task.lots'].create({
                    'name': lot.name,
                    'project_id': new_project.id,
                    'import_source': getattr(lot, 'import_source', False),
                })
                lot_mapping[lot.id] = new_lot.id
            except Exception as e:
                _logger.error("Failed creating lot %s: %s", lot.id, e)

        # -------------------------
        # Helper to build vals from original task + optional task_line override
        # -------------------------
        def _build_task_vals_from_original(original_task, task_line=None):
            vals = {
                'project_id': new_project.id,
                'company_id': company_id_int,
                'no': (task_line.no if task_line and task_line.no else original_task.no) or 'N/A',
                'name': (task_line.description or original_task.name) or (f"Task {original_task.id}"),
                'quantity': (task_line.quantity if task_line and task_line.quantity is not None else (
                        original_task.quantity or 0.0)),
                'unit_price': (task_line.unit_price if task_line and task_line.unit_price is not None else (
                        original_task.unit_price or 0.0)),
            }
            # unit
            if task_line and task_line.unit:
                vals['unit'] = task_line.unit.id
            elif getattr(original_task, 'unit', False):
                vals['unit'] = original_task.unit.id

            # lot mapping
            if task_line and task_line.lot_id and task_line.lot_id.id in lot_mapping:
                vals['lot_id'] = lot_mapping[task_line.lot_id.id]
            elif getattr(original_task, 'lot_id', False) and original_task.lot_id.id in lot_mapping:
                vals['lot_id'] = lot_mapping[original_task.lot_id.id]

            # copy import_source / flags / sequence if exist
            if hasattr(original_task, 'import_source'):
                vals['import_source'] = original_task.import_source
            if hasattr(original_task, 'is_title') and original_task.is_title:
                vals['is_title'] = True
            if hasattr(original_task, 'is_category') and original_task.is_category:
                vals['is_category'] = True
            if 'sequence' in original_task._fields and getattr(original_task, 'sequence', False):
                vals['sequence'] = original_task.sequence

            return vals

        # -------------------------
        # Build ordering (lot_sort_key and custom_sort_key)
        # -------------------------
        def custom_sort_key(task_line):
            if not task_line.no:
                return [999999]
            try:
                parts = str(task_line.no).split('.')
                return [int(p) if p.isdigit() else 0 for p in parts]
            except Exception:
                return [999999]

        has_lot_sequence_field = 'sequence' in lot_model._fields  # already computed above

        def lot_sort_key(task_line):
            if not task_line.lot_id:
                return (999999, '')
            if has_lot_sequence_field and getattr(task_line.lot_id, 'sequence', False):
                return (task_line.lot_id.sequence, task_line.lot_id.name or '')
            return (0, task_line.lot_id.name or '')

        # Check for sequence field on task_line model
        task_line_model = self.env['partner.task.line']
        has_sequence_field = 'sequence' in task_line_model._fields

        if has_sequence_field:
            all_tasks_ordered = self.task_line_ids.sorted(
                key=lambda r: (lot_sort_key(r), r.sequence if r.sequence else 999999, custom_sort_key(r))
            )
        else:
            all_tasks_ordered = self.task_line_ids.sorted(
                key=lambda r: (lot_sort_key(r), custom_sort_key(r))
            )

        # -------------------------
        # Create tasks preserving parent chain
        # -------------------------
        task_mapping = {}  # original_task_id -> new_task_id

        def ensure_parent_created(original_task):
            """Recursively ensure parent chain created; return new parent id or False."""
            if not original_task:
                return False
            if original_task.id in task_mapping:
                return task_mapping[original_task.id]
            parent = getattr(original_task, 'parent_id', False)
            new_parent_id = False
            if parent:
                new_parent_id = ensure_parent_created(parent)
            base_vals = _build_task_vals_from_original(original_task, None)
            base_vals['parent_id'] = new_parent_id or False
            try:
                created = self.env['custom.task'].create(base_vals)
            except Exception as e:
                _logger.error("Failed create base task for original %s: %s", original_task.id, e)
                # fallback minimal create
                base_min = {
                    'project_id': new_project.id,
                    'no': original_task.no or 'N/A',
                    'name': original_task.name or f"Task {original_task.id}",
                }
                created = self.env['custom.task'].create(base_min)
            task_mapping[original_task.id] = created.id
            return created.id

        def create_or_update_task_from_line(task_line):
            """Create or update a task from given task_line (uses mapping if original task already created)."""
            orig = task_line.task_id
            # if no original task, create simple task from line
            if not orig:
                vals = {
                    'project_id': new_project.id,
                    'no': task_line.no or 'N/A',
                    'name': task_line.description or f"Task from line {task_line.id}",
                    'quantity': task_line.quantity or 0.0,
                    'unit_price': task_line.unit_price or 0.0,
                }
                if task_line.unit:
                    vals['unit'] = task_line.unit.id
                if task_line.lot_id and task_line.lot_id.id in lot_mapping:
                    vals['lot_id'] = lot_mapping[task_line.lot_id.id]
                created = self.env['custom.task'].create(vals)
                task_mapping[('line', task_line.id)] = created.id
                return created.id

            # ensure parent chain exists
            parent_new_id = False
            if getattr(orig, 'parent_id', False):
                parent_new_id = ensure_parent_created(orig.parent_id)

            # if original was already created, update it with line values (don't duplicate)
            if orig.id in task_mapping:
                new_id = task_mapping[orig.id]
                update_vals = {
                    'no': task_line.no or orig.no,
                    'name': (task_line.description or orig.name) or f"Task {orig.id}",
                    'quantity': task_line.quantity if task_line.quantity is not None else (orig.quantity or 0.0),
                    'unit_price': task_line.unit_price if task_line.unit_price is not None else (
                            orig.unit_price or 0.0),
                    'parent_id': parent_new_id or False,
                }
                if task_line.unit:
                    update_vals['unit'] = task_line.unit.id
                if task_line.lot_id and task_line.lot_id.id in lot_mapping:
                    update_vals['lot_id'] = lot_mapping[task_line.lot_id.id]
                try:
                    self.env['custom.task'].browse(new_id).write(update_vals)
                except Exception as e:
                    _logger.warning("Failed update created task %s from line %s: %s", new_id, task_line.id, e)
                return new_id

            # otherwise create new task from original and line
            vals = _build_task_vals_from_original(orig, task_line)
            vals['parent_id'] = parent_new_id or False
            try:
                created = self.env['custom.task'].create(vals)
            except Exception as e:
                _logger.error("Error creating task from line %s: %s", task_line.id, e)
                minimal = {
                    'project_id': new_project.id,
                    'no': task_line.no or orig.no or 'N/A',
                    'name': task_line.description or orig.name or f"Task {orig.id}",
                    'quantity': task_line.quantity or 0.0,
                    'unit_price': task_line.unit_price or 0.0,
                    'parent_id': parent_new_id or False,
                }
                created = self.env['custom.task'].create(minimal)
            task_mapping[orig.id] = created.id
            return created.id

        # iterate in order and create/update
        for tl in all_tasks_ordered:
            try:
                create_or_update_task_from_line(tl)
            except Exception as e:
                _logger.error("Failed to create/update task for line %s: %s", tl.id, e)
                continue

        # return action to open the new project
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'custom.project',
            'res_id': new_project.id,
            'view_mode': 'form',
            'target': 'current',
            'name': f'New Project - {new_project.name}',
        }

    def open_situation(self):
        self.ensure_one()
        action = self.env.ref('custom_project.action_open_view_situation').sudo().read()[0]
        action['context'] = {
            'default_project_id': self.project_id.id,
            'default_original_subcontractor_id': self.original_subcontractor_id.id,
            'default_lots_id': [(6, 0, self.lots_id.ids)],
            'default_retenu_garantie': self.retenu_garantie.id,
            'default_retenu_realisation': self.retenu_realisation.id,
            # 'default_tva': self.tax_ids.id,
        }
        return action


class PartnerTaskLine(models.Model):
    _name = 'partner.task.line'
    _description = 'Ligne Tâche pour Partenaire'
    _rec_name = 'task_id'

    task_id_import_source = fields.Selection(
        related='task_id.import_source',
        string="Source Tache",
        store=True,
        readonly=True
    )

    # إضافة ترتيب افتراضي
    _order = "task_id_import_source"

    no = fields.Char("N")
    project_id = fields.Many2one('projects.associated', string="Partenaire", ondelete='cascade')
    project = fields.Many2one(related='project_id.project_id', string="Projet", store=True, readonly=True)
    task_id = fields.Many2one('custom.task', string="Tâche", domain="[('project_id', '=', project)]")
    description = fields.Text(string="Description")
    quantity_marche = fields.Float(string="Q.marché")
    quantity_restante = fields.Float(
        string="Q.restante",
        compute="_compute_quantity_restante",
        store=True,
        readonly=True,
    )
    quantity = fields.Float(string="Quantité", default=0.0)
    unit = fields.Many2one(related='task_id.unit', string="Unité", store=True)
    unit_price = fields.Float(string="P.U")
    total_price = fields.Float(string="Total HT", compute="_compute_total_price", store=True)
    lot_id = fields.Many2one('custom.task.lots', string="Lot", related='task_id.lot_id', store=True)
    is_child_task = fields.Boolean(string="Sous-tâche", compute='_compute_is_child_task', store=True)
    parent_task_id = fields.Many2one('custom.task', string="Tâche parente", compute='_compute_parent_task', store=True)
    amount_distributed = fields.Float(string="Montant Distribué", default=0.0)

    # Optional: level = fields.Integer(string="Niveau", default=0, store=True)  # si tu veux afficher indentation

    quantity_exceeds = fields.Boolean(
        string="Quantité dépasse",
        compute='_compute_quantity_exceeds',
        store=False,
        help="Vrai si la quantité dépasse la quantité du marché de la ligne "
             "ou si la somme totale (toutes conventions) dépasse la quantité du projet.",
    )

    @api.depends('quantity', 'quantity_marche', 'task_id', 'task_id.quantity',
                 'project_id', 'project_id.task_line_ids', 'project_id.task_line_ids.quantity')
    def _compute_quantity_exceeds(self):
        for rec in self:
            exceeds = False
            if rec.quantity_marche and (rec.quantity or 0.0) > rec.quantity_marche:
                exceeds = True
            elif rec.task_id and rec.task_id.quantity:
                current_assoc = rec.project_id
                current_real_id = (
                    current_assoc._origin.id
                    if current_assoc and isinstance(current_assoc._origin.id, int)
                    else False
                )
                # Quantité de la convention courante : lue en mémoire
                if current_assoc:
                    in_memory_qty = sum(
                        line.quantity or 0.0
                        for line in current_assoc.task_line_ids
                        if line.task_id == rec.task_id
                    )
                else:
                    in_memory_qty = rec.quantity or 0.0
                # Quantité des AUTRES conventions : lue en base, en excluant orphelines
                db_domain = [
                    ('task_id', '=', rec.task_id.id),
                    ('project_id', '!=', False),
                ]
                if current_real_id:
                    db_domain.append(('project_id', '!=', current_real_id))
                db_other_qty = sum(
                    self.env['partner.task.line'].search(db_domain).mapped('quantity')
                )
                if (in_memory_qty + db_other_qty) > rec.task_id.quantity:
                    exceeds = True
            rec.quantity_exceeds = exceeds

    @api.onchange('quantity', 'quantity_marche')
    def _onchange_quantity_warn_marche(self):
        """Avertit (sans bloquer) si la quantité saisie dépasse la quantité
        marché de la ligne. La ligne sera marquée en rouge dans la vue."""
        if self.quantity_marche and (self.quantity or 0.0) > self.quantity_marche:
            return {
                'warning': {
                    'title': _("Quantité du marché dépassée"),
                    'message': _(
                        "La quantité convention (%.2f) dépasse la quantité du marché (%.2f) "
                        "pour la tâche '%s'."
                    ) % (self.quantity, self.quantity_marche, self.task_id.name if self.task_id else ''),
                }
            }

    @api.onchange('original_subcontractor_id')
    def _onchange_original_subcontractor_id(self):
        """Recharger les quantités lorsque le sous-traitant change.
        Convention = quantité marché - quantités déjà allouées à d'autres
        sous-traitants pour la même tâche dans ce projet."""
        for rec in self:
            if rec.lots_id and rec.task_line_ids:
                for line in rec.task_line_ids:
                    if not line.task_id:
                        continue
                    allocated_to_others = rec._get_qty_allocated_to_other_subs(line.task_id)
                    line.quantity = max(
                        (line.quantity_marche or 0.0) - allocated_to_others, 0.0
                    )

    @api.depends('quantity', 'quantity_marche')
    def _compute_quantity_restante(self):
        for rec in self:
            marche = rec.quantity_marche or 0.0
            qty = rec.quantity or 0.0
            rec.quantity_restante = max(marche - qty, 0.0)

    @api.depends('task_id.parent_id')
    def _compute_is_child_task(self):
        for rec in self:
            rec.is_child_task = bool(rec.task_id and rec.task_id.parent_id)

    @api.depends('task_id.parent_id')
    def _compute_parent_task(self):
        for rec in self:
            rec.parent_task_id = rec.task_id.parent_id if rec.task_id else False

    @api.depends('quantity', 'unit_price')
    def _compute_total_price(self):
        for rec in self:
            rec.total_price = (rec.quantity or 0.0) * (rec.unit_price or 0.0)


class CustomProjectInherit(models.Model):
    _inherit = 'custom.project'

    nombre_achat = fields.Integer(string=' Achats liés')
    nombre_stock_article = fields.Integer(string='Stock', default=0, compute='_compute_nombre_stock_article')

    def open_custom_stock(self):
        return {
            'name': ('Stocks liés au projet: %s') % self.name,
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'res_model': 'custom.stock',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def _compute_nombre_stock_article(self):
        for rec in self:
            stock_count = self.env['custom.stock'].search_count([('project_id', '=', rec.id)])
            rec.nombre_stock_article = stock_count

    def _compute_nombre_achat(self):
        for project in self:
            project.nombre_achat = self.env['purchase.order'].search_count([('project_id', '=', project.id)])

    def open_related_purchases(self):
        return {
            'name': ('Achats liés au projet: %s') % self.name,
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'res_model': 'purchase.order',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }


class ResPartner(models.Model):
    _inherit = 'res.partner'

    contact_type = fields.Selection(
        [('SUPPLIER', 'Fournisseur'), ('CLIENT', 'Client'), ('SUBCONTRACTOR', 'Sous-traitant')], string='Contact Type',
        default='CLIENT')
    vat = fields.Char(string='N.I.F', index=True,
                      help="The Tax Identification Number. Complete it if the contact is subjected to government taxes. Used in some legal statements.")
    nis = fields.Char(string='N.I.S')
    ai = fields.Char(string='Article d\'imposition')
    company_registry = fields.Char(string='R.C')
    nombre_projets = fields.Integer(string="Convention", compute="_compute_nombre_projets")
    nombre_situations = fields.Integer(string="Nombre de Situations", compute="_compute_nombre_situations")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    def _compute_nombre_projets(self):
        for partner in self:
            if partner.contact_type == 'SUBCONTRACTOR':
                partner.nombre_projets = self.env['projects.associated'].search_count([
                    ('original_subcontractor_id', '=', partner.id)
                ])
            else:
                partner.nombre_projets = 0

    def _compute_nombre_situations(self):
        for partner in self:
            if partner.contact_type == 'SUBCONTRACTOR':
                partner.nombre_situations = self.env['situation'].search_count([
                    ('original_subcontractor_id', '=', partner.id)
                ])
            else:
                partner.nombre_situations = 0

    is_subcontractor = fields.Boolean(compute="_compute_is_subcontractor")
    task_lot_id = fields.Many2one('custom.task.lots', string="Lot de tâche",
                                  help="Lot associé aux tâches personnalisées")
    situation_count = fields.Integer(string="Situations", compute='_compute_situation_count')

    def _compute_situation_count(self):
        for partner in self:
            partner.situation_count = self.env['situation'].search_count(
                [('original_subcontractor_id', '=', partner.id)])




    def open_situat(self):
        self.ensure_one()
        return {
            'name': "Situations",
            'type': 'ir.actions.act_window',
            'res_model': 'situation',
            'view_mode': 'tree,form',
            'domain': [('original_subcontractor_id', '=', self.id)],
            'context': {'default_original_subcontractor_id': self.id},
        }

    def action_open_engagments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Engagments',
            'view_mode': 'tree,form',
            'res_model': 'projects.associated',
            'domain': [('original_subcontractor_id', '=', self.id)],

        }

    @api.depends('contact_type')
    def _compute_is_subcontractor(self):
        for rec in self:
            rec.is_subcontractor = rec.contact_type == 'SUBCONTRACTOR'

class RetenuGarantie(models.Model):
    _name = "retenu.garantie"
    _description = "Retenu de garantie"

    name = fields.Float(string="Nom", required=True)
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user)

class RetenuRealisation(models.Model):
    _name = "retenu.realisation"
    _description = "Retenu de réalisation"

    name = fields.Float(string="Nom", required=True)
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user)
