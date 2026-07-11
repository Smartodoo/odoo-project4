# -*- coding: utf-8 -*-
import base64
import io
import logging
import re
import traceback

from openpyxl import load_workbook
import html as pyhtml
import pandas as pd

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_round

_logger = logging.getLogger(__name__)


class CustomProject(models.Model):
    _name = "custom.project"
    _description = "Projet BTP"

    # Enhanced subtotal keywords constant
    SUBTOTAL_KEYWORDS = [
        'S/TOTAL', 'S-TOTAL', 'S_TOTAL', 'S TOTAL', 'SOUS-TOTAL', 'TOTAL PARTIEL', 'TOTAL GENERAL',
        'TOTAL LOT', 'SOUS TOTAL', 'SOUS-TOTAUX', 'SOUS TOTAUX', 'SOUS_TOTAUX',
        'SUB TOTAL', 'SUB-TOTAL', 'SUB_TOTAL', 'SUB/TOTAL',
        'TOTAUX', 'TOTAUX PARTIELS', 'TOTAUX GENERAUX',
        'SOMME', 'SOMME PARTIELLE', 'SOMME TOTALE'
    ]

    name = fields.Char('Nom du Projet', required=True)
    is_internal = fields.Boolean('Projet Interne ?', default=False)
    client_id = fields.Many2one(
        'res.partner',
        string='Contractant',
        domain="[('is_company', '=', True), ('contact_type', '=', 'CLIENT')]",
        required=True, ondelete='restrict'
    )
    description = fields.Text('Description')
    state = fields.Selection([('draft', 'Brouillon'), ('confirmed', 'Confirmé'),
                              ('done', 'Terminé'), ('cancelled', 'Annulé')],
                             string='État', default='draft')
    task_ids = fields.One2many('custom.task', 'project_id', string='Tâches', readonly=False)
    lots_ids = fields.One2many('custom.task.lots', 'project_id', string='Lots', readonly=False)





    # Primary file totals (19%)
    total_price = fields.Float(string='Total HT(E)', compute='_compute_total_price', store=True)
    tax_totale = fields.Float('Totale', compute='_compute_tax_totale', store=True)
    total = fields.Float('Total TTC', compute='_compute_total', store=True)

    # Secondary file totals (9%)
    total_price_2 = fields.Float(string='Total HT 2', compute='_compute_total_price_2', store=True)
    tax_totale_2 = fields.Float('Totale 2', compute='_compute_tax_totale_2', store=True)
    total_2 = fields.Float('Total TTC 2', compute='_compute_total_2', store=True)

    currency_id = fields.Many2one('res.currency', string='Devise', default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    total_intern = fields.Float('Total HT', compute='_compute_total_intern', store=True)
    co_contractor = fields.Many2one('res.partner',
                                    domain="[('is_company', '=', True), ('contact_type', '=', 'SUBCONTRACTOR'), ('company_id', '=', company_id)]",
                                    string="Co-Contractor")
    consumption_count = fields.Integer(
        string="Consommations",
        compute='_compute_consumption_count'
    )

    dashboard_html = fields.Html(
        string='Tableau de Bord',
        # compute='_compute_dashboard_html',
        # sanitize=False
    )
    observation_ids = fields.One2many(
        'custom.project.observation',
        'project_id',
        string='Prevision'
    )

    observation_count = fields.Integer(
        string='Prevision',
        compute='_compute_observation_count',
        store=False
    )

    open_observation_count = fields.Integer(
        string='Prevision',
        compute='_compute_open_observation_count',
        store=False
    )

    # Progress tracking fields
    progress = fields.Float(
        string='Progression (%)',
        compute='_compute_progress',
        store=True,
        help="Pourcentage de progression du projet basé sur les situations payées"
    )

    total_paid = fields.Float(
        string='Montant Payé',
        compute='_compute_payment_stats',
        store=True,
        help="Montant total payé pour ce projet"
    )

    total_remaining = fields.Float(
        string='Montant Restant',
        compute='_compute_payment_stats',
        store=True,
        help="Montant restant à payer"
    )

    situation_count = fields.Integer(
        string='Nombre de Situations',
        compute='_compute_situation_count',
        store=False
    )

    paid_situation_count = fields.Integer(
        string='Situations Payées',
        compute='_compute_situation_count',
        store=False
    )

    color = fields.Integer(string='Color Index', default=0)

    # Situation finale One2many
    situation_final_ids = fields.One2many(
        'situation.final',
        'project_id',
        string='Situations Finales'
    )

    situation_final_count = fields.Integer(
        string='Nombre Situations Finales',
        compute='_compute_situation_final_count',
        store=False
    )

    def _compute_situation_final_count(self):
        """Compute the number of final situations for this project"""
        for project in self:
            project.situation_final_count = len(project.situation_final_ids)

    def _compute_observation_count(self):
        for project in self:
            project.observation_count = self.env['custom.project.observation'].search_count([
                ('project_id', '=', project.id)
            ])

    def _compute_open_observation_count(self):
        for project in self:
            project.open_observation_count = self.env['custom.project.observation'].search_count([
                ('project_id', '=', project.id),

            ])

    def action_view_observations(self):
        """Open observations linked to this project"""
        self.ensure_one()
        return {
            'name': _('Observations'),
            'type': 'ir.actions.act_window',
            'res_model': 'custom.project.observation',
            'view_mode': 'tree,kanban,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,

            },
            'target': 'current',
        }

    def action_create_observation(self):
        """Create new observation for this project"""
        self.ensure_one()
        return {
            'name': _('Create Observation'),
            'type': 'ir.actions.act_window',
            'res_model': 'custom.project.observation',
            'view_mode': 'form',
            'context': {
                'default_project_id': self.id,
                'default_created_by_id': self.env.user.id,
            },
            'target': 'current',
        }




    def _compute_consumption_count(self):
        for project in self:
            project.consumption_count = self.env['cunsomation.stock'].search_count([
                ('project_id', '=', project.id)
            ])

    def action_view_consumptions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Consommations - {self.name}',
            'res_model': 'cunsomation.stock',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'search_default_project_id': self.id,
            }
        }

    @api.depends('total_price', 'total_price_2')
    def _compute_total_intern(self):
        for project in self:
            project.total_intern = project.total_price + project.total_price_2

    # Primary taxes with explicit relation table
    tax_ids = fields.Many2many(
        'account.tax',
        'custom_project_tax_primary_rel',
        'project_id',
        'tax_id',
        string='Taxes Principales (19%)'
    )

    # Secondary taxes with explicit relation table
    tax_ids_2 = fields.Many2many(
        'account.tax',
        'custom_project_tax_secondary_rel',
        'project_id',
        'tax_id',
        string='Taxes logments (9%)',
        domain="[('type_tax_use', '=', 'sale')]"
    )

    # Primary import file
    import_file = fields.Binary('Fichier Excel')
    import_filename = fields.Char('Nom fichier')

    # Secondary import file
    import_other_file = fields.Binary('Fichier Excel logments')
    import_other_filename = fields.Char('Nom fichier logments')

    # HTML previews
    table_html = fields.Html(string='Project Table', compute='_compute_table_html', sanitize=False)
    other_table_html = fields.Html(string='Project Table (logments)', compute='_compute_other_table_html',
                                   sanitize=False)

    # ---------- Enhanced Subtotal Detection Methods ----------
    def _contains_subtotal_keyword(self, row):
        """
        Enhanced subtotal keyword detection with more patterns and case insensitivity
        """
        if not row:
            return False

        # Combine all cells into one string for comprehensive checking
        row_text = ' '.join([str(cell) for cell in row if cell]).upper()

        # Extended list of subtotal patterns in multiple languages
        subtotal_patterns = [
            'SOUS TOTAL', 'SOUS-TOTAL', 'SOUS_TOTAL', 'SOUS/TOTAL',
            'S/TOTAL', 'S-TOTAL', 'S_TOTAL', 'S TOTAL',
            'TOTAL PARTIEL', 'TOTAL PARTIELLE',
            'TOTAL GENERAL', 'TOTAL GENERALE',
            'TOTAL LOT', 'TOTAL LOTS',
            'SUB TOTAL', 'SUB-TOTAL', 'SUB_TOTAL', 'SUB/TOTAL',
            'TOTAUX', 'TOTAUX PARTIELS', 'TOTAUX GENERAUX',
            'SOMME', 'SOMME PARTIELLE', 'SOMME TOTALE',
            'SOUS-TOTAUX', 'SOUS TOTAUX', 'SOUS_TOTAUX'
        ]

        # Check for any subtotal pattern
        for pattern in subtotal_patterns:
            if pattern in row_text:
                return True

        # Check for patterns like "S/ TOTAL", "S / TOTAL", etc.
        if re.search(r'S\s*[/\-\s]\s*TOTAL', row_text):
            return True

        # Check for lines that are mostly "TOTAL" with some prefixes
        if re.search(r'^[A-Z\s]*TOTAL[A-Z\s]*$', row_text) and len(row_text) < 50:
            return True

        return False

    def _looks_like_subtotal(self, text, row_text_upper=None):
        """
        Enhanced subtotal detection with more patterns
        """
        if not text and not row_text_upper:
            return False

        # Normalize text for comparison
        t = (str(text) if text else "").upper().strip()
        ru = (row_text_upper or "").upper().strip()

        # Extended patterns for subtotal detection
        patterns = [
            r'\bS[\s_/\\-]*TOTAL\b',
            r'\bSOUS[\s_/\\-]*TOTAL\b',
            r'\bSOUS[\s_/\\-]*TOTAUX\b',
            r'\bTOTAL\s+PARTIEL\b',
            r'\bTOTAL\s+LOT\b',
            r'\bTOTAL\s+[A-Z]+\b',
            r'\bS\.TOTAL\b',
            r'\bSTOTAL\b',
            r'\bTOTAL\s+S/\b',
            r'\bTOTAL\s+GENERAL\b',
            r'\bTOTAL\s+DU\b',
            r'\bTOTAL\s+DES\b',
            r'\bSOMME\s+PARTIELLE\b',
            r'\bSOMME\s+TOTALE\b'
        ]

        # Check patterns in both text and row_text_upper
        for pattern in patterns:
            if re.search(pattern, t) or re.search(pattern, ru):
                return True

        # Additional direct matches
        direct_matches = [
            'S/TOTAL', 'S-TOTAL', 'S_TOTAL', 'S TOTAL',
            'SOUS-TOTAL', 'SOUS TOTAL', 'SOUS_TOTAL',
            'TOTAL PARTIEL', 'TOTAL GENERAL', 'TOTAL LOT',
            'SOUS-TOTAUX', 'SOUS TOTAUX', 'SOUS_TOTAUX',
            'SUB TOTAL', 'SUB-TOTAL', 'TOTAUX'
        ]

        for match in direct_matches:
            if match in t or match in ru:
                return True

        # Match lines starting with S/ followed by text (common in French documents)
        if re.match(r'^S\/\s*\w+', t) or re.match(r'^S\s+\w+', t):
            return True

        # Match lines that are mostly "TOTAL" with some prefixes
        if t.startswith('TOTAL') and len(t) < 20:
            return True

        return False

    # ---------- UOM Management ----------
    def _get_or_create_uom(self, unit_name):
        """Get or create UOM based on unit name"""
        if not unit_name:
            return False

        # Clean unit name
        unit_name = str(unit_name).strip().upper()
        if not unit_name or len(unit_name) > 20:
            return False

        try:
            # Common unit mappings
            unit_mappings = {
                'F': 'Unité',
                'U': 'Unité',
                'ML': 'Mètre Linéaire',
                'M2': 'Mètre Carré',
                'M3': 'Mètre Cube',
                'M': 'Mètre',
                'KG': 'Kilogramme',
                'T': 'Tonne',
                'L': 'Litre',
                'P': 'Pièce',
                'UNITE': 'Unité',
                'UNIT': 'Unité',
                'M²': 'Mètre Carré',
                'M³': 'Mètre Cube',
                'ENS': 'Ensemble',
                'M2': 'Mètre Carré',
                'M3': 'Mètre Cube'
            }

            # Get the proper unit name from mapping
            search_name = unit_mappings.get(unit_name, unit_name)

            # Search for existing UOM
            uom = self.env['uom.uom'].search([
                '|', ('name', '=ilike', search_name),
                ('name', '=ilike', unit_name)
            ], limit=1)

            if uom:
                return uom

            # Create new UOM if not found
            uom_category = self.env['uom.category'].search([], limit=1)
            if not uom_category:
                uom_category = self.env['uom.category'].create({
                    'name': 'Unités de mesure'
                })

            uom = self.env['uom.uom'].create({
                'name': search_name,
                'category_id': uom_category.id,
                'uom_type': 'reference',
                'factor': 1.0,
                'rounding': 0.001,
                'company_id': self.env.company.id,
            })

            _logger.info("✅ Created new UOM: %s", search_name)
            return uom

        except Exception as e:
            _logger.error("Error creating UOM %s: %s", unit_name, str(e))
            return False

    # ---------- Calculation Methods ----------
    @api.depends('lots_ids.s_total')
    def _compute_total_price(self):
        """Compute total HT for primary file (services) - 19% tax"""
        for project in self:
            total = 0.0
            # Sum s_total from primary lots
            primary_lots = project.lots_ids.filtered(lambda l: l.import_source == 'primary')
            for lot in primary_lots:
                total += lot.s_total or 0.0
            project.total_price = float_round(total, precision_digits=2)

    @api.depends('total_price', 'tax_ids.amount', 'tax_ids.amount_type')
    def _compute_tax_totale(self):
        """Compute TVA 19% for primary file (services)"""
        for project in self:
            tax_total = 0.0
            base = project.total_price or 0.0
            for tax in project.tax_ids:
                try:
                    if tax.amount_type == 'percent':
                        tax_total += base * (tax.amount or 0.0) / 100.0
                    elif tax.amount_type == 'fixed':
                        tax_total += (tax.amount or 0.0)
                    else:
                        tax_total += base * (tax.amount or 0.0) / 100.0
                except Exception:
                    _logger.exception("Erreur calcul taxe pour project %s", project.id)
            project.tax_totale = float_round(tax_total, precision_digits=2)

    @api.depends('total_price', 'tax_totale')
    def _compute_total(self):
        """Compute total TTC for primary file (services)"""
        for project in self:
            project.total = float_round((project.total_price or 0.0) + (project.tax_totale or 0.0), precision_digits=2)

    @api.depends('lots_ids.s_total')
    def _compute_total_price_2(self):
        """Compute total HT for secondary file (logments) - 9% tax"""
        for project in self:
            total = 0.0
            # Sum s_total from secondary lots
            secondary_lots = project.lots_ids.filtered(lambda l: l.import_source == 'secondary')
            for lot in secondary_lots:
                total += lot.s_total or 0.0
            project.total_price_2 = float_round(total, precision_digits=2)

    @api.depends('total_price_2', 'tax_ids_2.amount', 'tax_ids_2.amount_type')
    def _compute_tax_totale_2(self):
        """Compute TVA 9% for secondary file (logments)"""
        for project in self:
            tax_total = 0.0
            base = project.total_price_2 or 0.0
            for tax in project.tax_ids_2:
                try:
                    if tax.amount_type == 'percent':
                        tax_total += base * (tax.amount or 0.0) / 100.0
                    elif tax.amount_type == 'fixed':
                        tax_total += (tax.amount or 0.0)
                    else:
                        tax_total += base * (tax.amount or 0.0) / 100.0
                except Exception:
                    _logger.exception("Erreur calcul taxe secondaire pour project %s", project.id)
            project.tax_totale_2 = float_round(tax_total, precision_digits=2)

    @api.depends('total_price_2', 'tax_totale_2')
    def _compute_total_2(self):
        """Compute total TTC for secondary file (logments)"""
        for project in self:
            project.total_2 = float_round((project.total_price_2 or 0.0) + (project.tax_totale_2 or 0.0),
                                          precision_digits=2)

    # ---------- Helpers ----------
    def _clean_cell(self, v):
        if v is None:
            return None
        try:
            if isinstance(v, float) and pd.isna(v):
                return None
        except Exception:
            pass
        s = str(v).strip()
        if s == '':
            return None
        s = s.replace('\xa0', ' ')
        s = re.sub(r'\s+', ' ', s)
        return s

    def _is_numeric_like(self, v):
        if v is None:
            return False
        s = str(v).strip()
        if s == '':
            return False
        s2 = s.replace('\xa0', '').replace(' ', '')
        return bool(re.match(r'^[\+\-]?\d[\d\.,]*$', s2))

    def _parse_number(self, value):
        try:
            if value is None:
                return 0.0
            if isinstance(value, (int, float)):
                return float(value)
            s = str(value).strip()
            if s == '':
                return 0.0
            s = s.replace('\xa0', '').replace(' ', '')
            if ',' in s and '.' in s:
                if s.rfind(',') > s.rfind('.'):
                    s = s.replace('.', '').replace(',', '.')
                else:
                    s = s.replace(',', '')
            elif ',' in s and '.' not in s:
                s = s.replace(',', '.')
            s = re.sub(r'[^\d\.\-]', '', s)
            return float(s) if s not in ('', '.', '-') else 0.0
        except Exception:
            return 0.0

    def _format_number(self, value, decimals=3):
        try:
            if value is None:
                fmt = "{:,.{prec}f}".format(0.0, prec=decimals)
                return fmt.replace(",", " ").replace(".", ",")
            fmt = "{:,.{prec}f}".format(float(value), prec=decimals)
            return fmt.replace(",", " ").replace(".", ",")
        except Exception:
            return str(value or "")

    def _split_multiline_cell(self, sraw):
        if not sraw:
            return []
        lines = [l.strip() for l in re.split(r'[\r\n]+', str(sraw)) if l and l.strip()]
        return lines

    def _parse_subline_tokens(self, line):
        desc = ''
        unit_text = ''
        qty = price = amount = 0.0
        tokens = re.split(r'\t|\s{2,}|\s+', line)
        tokens = [t for t in tokens if t is not None and str(t).strip() != '']
        numeric_idx = [i for i, t in enumerate(tokens) if self._is_numeric_like(t)]
        if numeric_idx:
            amount_idx = numeric_idx[-1]
            price_idx = numeric_idx[-2] if len(numeric_idx) >= 2 else None
            qty_idx = numeric_idx[-3] if len(numeric_idx) >= 3 else None
            if qty_idx is not None:
                qty = self._parse_number(tokens[qty_idx])
            if price_idx is not None:
                price = self._parse_number(tokens[price_idx])
            if amount_idx is not None:
                amount = self._parse_number(tokens[amount_idx])
            if qty_idx is not None and qty_idx - 1 >= 0:
                cand = tokens[qty_idx - 1]
                if cand and not self._is_numeric_like(cand) and len(cand) <= 8:
                    unit_text = cand
            if numeric_idx:
                first_num = numeric_idx[0]
                if first_num > 0:
                    desc = ' '.join(tokens[:first_num])
        else:
            desc = line
        return desc.strip(), (unit_text or '').strip(), qty, price, amount

    def _ensure_tva_19(self):
        """Ensure 19% tax exists"""
        company = self.env.company
        tax = self.env['account.tax'].search([
            ('company_id', '=', company.id),
            ('amount', '=', 19.0),
            ('type_tax_use', '=', 'sale')
        ], limit=1)
        if not tax:
            tax = self.env['account.tax'].create({
                'name': 'TVA 19%',
                'amount': 19.0,
                'amount_type': 'percent',
                'type_tax_use': 'sale',
                'company_id': company.id,
            })
        return tax

    def _ensure_tva_9(self):
        """Ensure 9% tax exists"""
        company = self.env.company
        tax = self.env['account.tax'].search([
            ('company_id', '=', company.id),
            ('amount', '=', 9.0),
            ('type_tax_use', '=', 'sale')
        ], limit=1)
        if not tax:
            tax = self.env['account.tax'].create({
                'name': 'TVA 9%',
                'amount': 9.0,
                'amount_type': 'percent',
                'type_tax_use': 'sale',
                'company_id': company.id,
            })
        return tax

    def _process_sheet_table_only(self, xls, sheet_name, suffix='', source='primary'):
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=object, engine="openpyxl")
        except Exception:
            df = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=object)

        clean_matrix = []
        for idx, row in df.iterrows():
            clean_matrix.append([self._clean_cell(c) for c in row.tolist()])

        # Find header row
        header_row_idx = None
        main_headers = {'DESGNATION', 'DESIGNATION', 'QUANTITES', 'QUANTITE', 'PRIX', 'MONTANT', 'U', 'UNITE'}
        for i, row in enumerate(clean_matrix[:160]):
            row_text = ' '.join([str(c).upper() for c in row if c])
            if not row_text:
                continue
            count = sum(1 for k in main_headers if k in row_text)
            if count >= 2:
                header_row_idx = i
                break
        if header_row_idx is None:
            _logger.info("No table header found in sheet %s - skipping", sheet_name)
            return

        start_idx = header_row_idx + 1
        sequence = 10
        current_lot = None
        current_section = None
        current_parent_task = None
        task_code_map = {}
        _suffix = suffix or ''
        _source = source or 'primary'

        for ri in range(start_idx, len(clean_matrix)):
            try:
                row = clean_matrix[ri]

                # ========== ENHANCED SUBTOTAL KEYWORD DETECTION ==========
                # Skip entire row if any cell contains subtotal keywords
                if self._contains_subtotal_keyword(row):
                    _logger.info("🚫 SKIPPING SUBTOTAL ROW: %s", [str(c) for c in row if c])
                    continue
                # ========== END SUBTOTAL KEYWORD DETECTION ==========

                if all(c is None for c in row):
                    continue
                row_text_upper = ' '.join([str(c).upper() for c in row if c]).strip()
                if row_text_upper and re.match(r'^[\d\.,\s\-\+]+$', row_text_upper):
                    # skip numeric-only footers/lines
                    continue

                first_non = next((c for c in row if c), None)
                if first_non:
                    first_up = str(first_non).upper()
                    if any(kw in first_up for kw in ['PROJET', 'ATTACH', 'ATTACHEMENT', 'TVA', 'TOTAL EN']):
                        continue

                # ========== ENHANCED SUBTOTAL DETECTION AND HANDLING ==========
                # Check if this is a subtotal line using multiple strategies
                is_subtotal_line = False
                subtotal_keywords = ['S/TOTAL', 'SOUS-TOTAL', 'SOUS TOTAL', 'TOTAL PARTIEL', 'TOTAL LOT', 'TOTAL S/']

                # Check if this is a subtotal line using multiple strategies
                if row_text_upper:
                    # Strategy 1: Use the existing pattern matching
                    is_subtotal_line = self._looks_like_subtotal(row_text_upper)

                    # Strategy 2: Direct keyword matching in row text
                    if not is_subtotal_line:
                        for keyword in subtotal_keywords:
                            if keyword in row_text_upper:
                                is_subtotal_line = True
                                break

                    # Strategy 3: Check first cell for subtotal patterns
                    if not is_subtotal_line and first_non:
                        first_cell_upper = str(first_non).upper()
                        for keyword in subtotal_keywords:
                            if keyword in first_cell_upper:
                                is_subtotal_line = True
                                break
                        # Also check for patterns like "S/ TOTAL", "S / TOTAL", etc.
                        if re.match(r'^S[/\s]*TOTAL', first_cell_upper):
                            is_subtotal_line = True

                if is_subtotal_line:
                    _logger.info("🔍 SUBTOTAL DETECTED: %s", row_text_upper)
                    # Skip creating any task for subtotal lines
                    continue
                # ========== END SUBTOTAL HANDLING ==========

                # Detect LOT by numeric-first-cell + text after (e.g. "1 Designation...")
                non_empty = [c for c in row if c]
                if non_empty and isinstance(non_empty[0], str):
                    first_val = non_empty[0].strip()
                    if re.match(r'^\d+$', first_val):
                        others_numeric = any(self._is_numeric_like(c) for c in row[1:])
                        has_text_after = any(c and (not self._is_numeric_like(c)) for c in row[1:])
                        if (not others_numeric) and has_text_after:
                            lot_name = " ".join([str(c) for c in row if c])
                            try:
                                with self.env.cr.savepoint():
                                    current_lot = self.env['custom.task.lots'].create({
                                        'name': (lot_name or '') + _suffix,
                                        'project_id': self.id,
                                        'sequence': sequence,
                                        'company_id': self.env.company.id,
                                        'import_source': _source,
                                    })
                            except Exception as e:
                                _logger.exception("Failed create lot '%s' (sheet %s row %s): %s", lot_name, sheet_name,
                                                  ri, e)
                                current_lot = None
                            sequence += 10
                            current_section = None
                            current_parent_task = None
                            task_code_map = {}
                            continue

                # Explicit LOT lines
                if non_empty and isinstance(non_empty[0], str) and (
                        any(k in non_empty[0].upper() for k in ('LOT N°', 'LOT N', 'LOT:')) or non_empty[
                    0].strip().upper().startswith('LOT ')):
                    lot_name = non_empty[0]
                    try:
                        with self.env.cr.savepoint():
                            current_lot = self.env['custom.task.lots'].create({
                                'name': (lot_name or '') + _suffix,
                                'project_id': self.id,
                                'sequence': sequence,
                                'company_id': self.env.company.id,
                                'import_source': _source,
                            })
                    except Exception as e:
                        _logger.exception("Failed create lot '%s' (sheet %s row %s): %s", lot_name, sheet_name, ri, e)
                        current_lot = None
                    sequence += 10
                    current_section = None
                    current_parent_task = None
                    task_code_map = {}
                    continue

                # Title detection: lines starting with 'a/' etc.
                first_non_index = None
                first_non_cell = None
                for i_c, c in enumerate(row):
                    if c:
                        first_non_index = i_c
                        first_non_cell = c
                        break
                title_match = False
                if first_non_cell and isinstance(first_non_cell, str) and re.match(r'^[A-Za-z]\/',
                                                                                   first_non_cell.strip()):
                    title_match = True

                if title_match:
                    title_parts = []
                    txt = re.sub(r'^[A-Za-z]\/\s*', '', str(first_non_cell).strip())
                    title_parts.append(txt)
                    for j in range(first_non_index + 1, len(row)):
                        if row[j] and not self._is_numeric_like(row[j]):
                            title_parts.append(str(row[j]))
                    full_title = " ".join([p for p in title_parts if p]).strip()
                    if not full_title:
                        full_title = str(first_non_cell).strip()

                    title_vals = {
                        'no': '',
                        'name': full_title,
                        'unit_name': '',
                        'quantity': 0.0,
                        'unit_price': 0.0,
                        'is_title': True,
                        'is_category': True,
                        'project_id': self.id,
                        'sequence': sequence,
                        'company_id': self.env.company.id,
                        'import_source': _source,
                    }
                    if current_lot:
                        title_vals['lot_id'] = current_lot.id
                    try:
                        with self.env.cr.savepoint():
                            self.env['custom.task'].create(title_vals)
                    except Exception as e:
                        _logger.exception("Failed create title line (sheet %s row %s): %s", sheet_name, ri, e)
                    sequence += 5
                    continue

                # Find numeric code like 6.08, 1.2.3 ...
                code_idx = None
                code_val = None
                for i, c in enumerate(row):
                    if c and re.match(r'^\d+(\.\d+)*$', str(c).strip()):
                        code_idx = i
                        code_val = str(c).strip()
                        break

                if code_val:
                    # Additional safeguard: Check if this is actually a subtotal line disguised as a code
                    row_desc = ' '.join([str(c) for c in row if c and not self._is_numeric_like(c)]).upper()
                    if self._looks_like_subtotal(row_desc):
                        _logger.info("🚫 Skipping subtotal line disguised as code: %s", row_desc)
                        continue

                    dot_count = code_val.count('.')
                    is_section = (dot_count == 1)
                    is_task = (dot_count == 2)
                    is_subtask = (dot_count >= 3)

                    raw_cell = df.iloc[ri, code_idx] if code_idx is not None else None
                    desc = ''
                    if raw_cell:
                        sraw = str(raw_cell).strip()
                        parts = re.split(r'\t|\n{1,}|\s{2,}', sraw)
                        if len(parts) > 1:
                            desc = " ".join(parts[1:]).strip()
                    if not desc:
                        for j in range(code_idx + 1, min(len(row), code_idx + 6)):
                            if row[j] and not self._is_numeric_like(row[j]):
                                desc = (desc + ' ' + row[j]).strip()

                    # Robust fallback for empty desc
                    if not desc or len(desc.strip()) <= 2:
                        text_cells = []
                        for j in range(code_idx + 1, min(len(row), code_idx + 8)):
                            if row[j] and not self._is_numeric_like(row[j]):
                                text_cells.append(str(row[j]).strip())
                        if text_cells:
                            desc = ' '.join(text_cells).strip()
                        else:
                            if raw_cell:
                                desc = re.sub(r'^\d+(\.\d+)*\s*', '', str(raw_cell)).strip()

                    # Handle multiline parent with explicit sub-lines inside same cell
                    multiline_lines = self._split_multiline_cell(raw_cell) if raw_cell else []
                    handled_multiline = False
                    if len(multiline_lines) > 1:
                        has_numeric_in_sublines = any(
                            any(self._is_numeric_like(t) for t in re.split(r'\t|\s{2,}|\s+', ln))
                            for ln in multiline_lines[1:]
                        )
                        if has_numeric_in_sublines:
                            parent_no = f"{code_val}.01"
                            parent_name = multiline_lines[0]
                            parent_name = re.sub(r'^\d+(\.\d+)*\s*', '', parent_name).strip()

                            parent_vals = {
                                'no': parent_no,
                                'name': parent_name,
                                'unit_name': '',
                                'quantity': 0.0,
                                'unit_price': 0.0,
                                'project_id': self.id,
                                'sequence': sequence,
                                'company_id': self.env.company.id,
                                'import_source': _source,
                            }
                            if current_lot:
                                parent_vals['lot_id'] = current_lot.id
                            try:
                                with self.env.cr.savepoint():
                                    parent_task = self.env['custom.task'].create(parent_vals)
                                    current_parent_task = parent_task
                                    task_code_map[parent_no] = parent_task
                            except Exception as e:
                                _logger.exception("Failed create parent (multiline) %s (sheet %s row %s): %s",
                                                  parent_no, sheet_name, ri, e)
                                parent_task = None
                                current_parent_task = None

                            sequence += 10

                            idx_sub = 2
                            for ln in multiline_lines[1:]:
                                sub_code = f"{code_val}.{idx_sub:02d}"
                                sdesc, sunit, sqty, sprice, samount = self._parse_subline_tokens(ln)

                                # fallback for empty sdesc: strip bullets, then take non-numeric tokens
                                sdesc = (sdesc or '').strip()
                                if not sdesc:
                                    ln_text = str(ln).strip()
                                    ln_text = re.sub(r'^\d+(\.\d+)*\s*', '', ln_text)
                                    ln_text = re.sub(r'^[A-Za-z]\)\s*', '', ln_text)
                                    parts = [p for p in re.split(r'\t|\s{2,}|\s+', ln_text) if
                                             p and not self._is_numeric_like(p)]
                                    sdesc = ' '.join(parts).strip() if parts else ln_text.strip()

                                sub_vals = {
                                    'no': sub_code,
                                    'name': sdesc,
                                    'unit_name': sunit or '',
                                    'quantity': sqty or 0.0,
                                    'unit_price': sprice or 0.0,
                                    'project_id': self.id,
                                    'parent_id': parent_task.id if parent_task else None,
                                    'sequence': sequence,
                                    'company_id': self.env.company.id,
                                    'import_source': _source,
                                }
                                if current_lot:
                                    sub_vals['lot_id'] = current_lot.id

                                if sunit:
                                    uom = self._get_or_create_uom(sunit)
                                    if uom:
                                        sub_vals['unit'] = uom.id

                                try:
                                    with self.env.cr.savepoint():
                                        self.env['custom.task'].create(sub_vals)
                                except Exception as e:
                                    _logger.exception("Failed create multiline sub-task %s (sheet %s row %s): %s",
                                                      sub_code, sheet_name, ri, e)

                                idx_sub += 1
                                sequence += 10

                            handled_multiline = True

                    if handled_multiline:
                        continue

                    # ========== CORRECTED UNIT EXTRACTION ==========
                    # numeric extraction for single-row tasks/subtasks
                    numeric_idx = [i for i, c in enumerate(row) if c and self._is_numeric_like(c)]
                    qty = price = amount = 0.0
                    unit_text = ''

                    # Common unit symbols for detection
                    unit_symbols = ['F', 'U', 'ML', 'M2', 'M3', 'M', 'KG', 'T', 'L', 'P', 'UNITE', 'UNIT', 'M²', 'M³',
                                    'ENS']

                    if numeric_idx:
                        amount_idx = numeric_idx[-1]
                        price_idx = numeric_idx[-2] if len(numeric_idx) >= 2 else None
                        qty_idx = numeric_idx[-3] if len(numeric_idx) >= 3 else None

                        if qty_idx is not None:
                            qty = self._parse_number(df.iloc[ri, qty_idx])
                        if price_idx is not None:
                            price = self._parse_number(df.iloc[ri, price_idx])
                        if amount_idx is not None:
                            amount = self._parse_number(df.iloc[ri, amount_idx])

                        # Strategy 1: Look for unit in the cell before quantity
                        if qty_idx is not None and qty_idx - 1 >= 0:
                            cand = row[qty_idx - 1]
                            if cand and cand.upper() in unit_symbols:
                                unit_text = cand
                                # Remove unit from description if it was included
                                if desc.endswith(unit_text):
                                    desc = desc[:-len(unit_text)].strip()

                        # Strategy 2: Look for unit in specific columns
                        if not unit_text:
                            # Check common unit column positions
                            unit_positions = [code_idx + 2, code_idx + 3, 2, 3]  # Common positions for unit column
                            for pos in unit_positions:
                                if pos < len(row) and row[pos] and row[pos].upper() in unit_symbols:
                                    unit_text = row[pos]
                                    # Remove unit from description if it was included
                                    if desc.endswith(unit_text):
                                        desc = desc[:-len(unit_text)].strip()
                                    break

                        # Strategy 3: Look for unit in the row
                        if not unit_text:
                            for k in range(len(row)):
                                if row[k] and row[k].upper() in unit_symbols:
                                    unit_text = row[k]
                                    # Remove unit from description if it was included
                                    if desc.endswith(unit_text):
                                        desc = desc[:-len(unit_text)].strip()
                                    break

                    if (not price or price == 0.0) and qty and amount:
                        try:
                            price = amount / qty
                        except Exception:
                            price = 0.0

                    # Skip if description contains subtotal keywords
                    if any(k in (desc or "").upper() for k in self.SUBTOTAL_KEYWORDS):
                        continue

                    # Clean the description - remove any trailing unit symbols
                    if desc:
                        for unit_symbol in unit_symbols:
                            if desc.upper().endswith(unit_symbol):
                                desc = desc[:-len(unit_symbol)].strip()
                                if not unit_text:
                                    unit_text = unit_symbol
                                break

                    # build main vals. Only set 'no' for section/task (not deeper subtasks)
                    vals = {
                        'name': desc,
                        'unit_name': unit_text,
                        'quantity': qty,
                        'unit_price': price,
                        'project_id': self.id,
                        'sequence': sequence,
                        'company_id': self.env.company.id,
                        'import_source': _source,
                    }
                    if current_lot:
                        vals['lot_id'] = current_lot.id

                    # parent resolution
                    parent_id = False
                    if is_section:
                        parent_id = False
                    elif is_task:
                        parent_id = current_section.id if current_section else False
                    elif is_subtask:
                        parent_code = '.'.join(code_val.split('.')[:-1])
                        parent_task = task_code_map.get(parent_code)
                        if parent_task:
                            parent_id = parent_task.id
                        elif current_parent_task:
                            parent_id = current_parent_task.id

                    if parent_id:
                        vals['parent_id'] = parent_id

                    if code_val and [is_subtask, is_section, is_task]:
                        vals['no'] = code_val

                    if unit_text:
                        uom = self._get_or_create_uom(unit_text)
                        if uom:
                            vals['unit'] = uom.id

                    try:
                        with self.env.cr.savepoint():
                            new_task = self.env['custom.task'].create(vals)
                            task_code_map[code_val] = new_task
                            if is_section:
                                current_section = new_task
                                current_parent_task = None
                            elif is_task:
                                current_parent_task = new_task
                    except Exception as e:
                        _logger.exception("Failed create task %s (sheet %s row %s): %s", code_val, sheet_name, ri, e)

                    sequence += 10
                    continue

                # ========== IMPROVED UNIT-CODED SUBTASKS ==========
                has_unit_code = False
                unit_code = None
                unit_code_index = None

                # Look for unit symbols in the first few columns
                for i in range(min(4, len(row))):
                    if row[i] and isinstance(row[i], str):
                        cell_upper = row[i].strip().upper()
                        unit_symbols = ['F', 'U', 'ML', 'M2', 'M3', 'M', 'KG', 'T', 'L', 'P', 'UNITE', 'UNIT', 'M²',
                                        'M³']
                        if cell_upper in unit_symbols:
                            has_unit_code = True
                            unit_code = cell_upper
                            unit_code_index = i
                            break

                if has_unit_code and current_parent_task:
                    # Check if this unit-coded line contains subtotal keywords
                    if self._contains_subtotal_keyword(row):
                        _logger.info("🚫 Skipping subtotal line in unit-coded section: %s", row)
                        continue

                    # Build description from surrounding cells
                    description_parts = []

                    # Search in cells before and after unit code
                    search_range = []
                    if unit_code_index > 0:
                        search_range.extend(range(0, unit_code_index))
                    if unit_code_index + 1 < len(row):
                        search_range.extend(range(unit_code_index + 1, min(unit_code_index + 4, len(row))))

                    for j in search_range:
                        if (row[j] and not self._is_numeric_like(row[j]) and
                                j != unit_code_index and
                                row[j].strip().upper() not in unit_symbols):

                            cell_content = str(row[j]).strip()
                            cell_content = re.sub(r'^[\-\*\.\s]+|[\-\*\.\s]+$', '', cell_content)
                            if cell_content and len(cell_content) > 1:
                                description_parts.append(cell_content)

                    # Create smart description
                    if not description_parts and current_parent_task.name:
                        unit_descriptions = {
                            'F': 'Forfait', 'U': 'Unité', 'ML': 'Mètre Linéaire', 'M2': 'Mètre Carré',
                            'M3': 'Mètre Cube', 'M': 'Mètre', 'KG': 'Kilogramme', 'T': 'Tonne',
                            'L': 'Litre', 'P': 'Pièce'
                        }
                        unit_desc = unit_descriptions.get(unit_code, unit_code)
                        parent_name_short = current_parent_task.name
                        if len(parent_name_short) > 50:
                            parent_name_short = parent_name_short[:47] + "..."
                        sub_desc = f"{parent_name_short} - {unit_desc}"
                    elif description_parts:
                        sub_desc = ' '.join(description_parts)
                    else:
                        sub_desc = f"Tâche {unit_code}"

                    # Extract numeric values
                    sub_numeric_idx = [i for i, c in enumerate(row) if c and self._is_numeric_like(c)]
                    sub_qty = sub_price = sub_amount = 0.0

                    if sub_numeric_idx:
                        if len(sub_numeric_idx) == 1:
                            sub_amount = self._parse_number(df.iloc[ri, sub_numeric_idx[0]])
                        elif len(sub_numeric_idx) == 2:
                            sub_qty = self._parse_number(df.iloc[ri, sub_numeric_idx[0]])
                            sub_amount = self._parse_number(df.iloc[ri, sub_numeric_idx[1]])
                        elif len(sub_numeric_idx) >= 3:
                            sub_qty = self._parse_number(df.iloc[ri, sub_numeric_idx[0]])
                            sub_price = self._parse_number(df.iloc[ri, sub_numeric_idx[1]])
                            sub_amount = self._parse_number(df.iloc[ri, sub_numeric_idx[2]])

                        if sub_amount == 0.0 and sub_qty != 0.0 and sub_price != 0.0:
                            sub_amount = float_round(sub_qty * sub_price, precision_digits=2)
                        elif (sub_price == 0.0) and sub_qty != 0.0 and sub_amount != 0.0:
                            sub_price = float_round(sub_amount / sub_qty, precision_digits=2) if sub_qty != 0.0 else 0.0

                    # Create subtask
                    parent_no = current_parent_task.no if current_parent_task and current_parent_task.no else ""
                    if parent_no:
                        existing_subtasks = self.env['custom.task'].search([
                            ('parent_id', '=', current_parent_task.id),
                            ('project_id', '=', self.id)
                        ])
                        sub_code_number = len(existing_subtasks) + 1
                        no = f"{parent_no}.{sub_code_number:02d}"
                    else:
                        no = f"SUB.{sequence:03d}"

                    sub_vals = {
                        'no': no,
                        'name': sub_desc,
                        'unit_name': unit_code,
                        'quantity': sub_qty,
                        'unit_price': sub_price,
                        'project_id': self.id,
                        'parent_id': current_parent_task.id,
                        'sequence': sequence,
                        'company_id': self.env.company.id,
                        'import_source': _source,
                    }

                    if current_lot:
                        sub_vals['lot_id'] = current_lot.id

                    if unit_code:
                        uom = self._get_or_create_uom(unit_code)
                        if uom:
                            sub_vals['unit'] = uom.id

                    try:
                        with self.env.cr.savepoint():
                            new_subtask = self.env['custom.task'].create(sub_vals)
                    except Exception as e:
                        _logger.exception("Failed create unit-coded subtask (sheet %s row %s): %s", sheet_name, ri, e)

                    sequence += 10
                    continue

                # Continuation lines
                text_cells = [c for c in row if c and not self._is_numeric_like(c)]
                if text_cells:
                    continuation_text = ' '.join(text_cells)
                    if any(keyword in continuation_text.upper() for keyword in self.SUBTOTAL_KEYWORDS):
                        _logger.info("🚫 Skipping subtotal continuation text: %s", continuation_text)
                        continue

                    try:
                        with self.env.cr.savepoint():
                            last = self.env['custom.task'].search([('project_id', '=', self.id)], order='id desc',
                                                                  limit=1)
                            if last and len(continuation_text.strip()) > 2:
                                last.write({'name': (last.name or '') + ' ' + continuation_text})
                    except Exception as e:
                        _logger.exception("Failed append continuation (sheet %s row %s): %s", sheet_name, ri, e)
                    continue

            except Exception as e_row:
                _logger.exception("Error parsing row %s sheet %s: %s", ri, sheet_name, e_row)
                continue

    # ... [rest of the methods remain the same - import_excel_file, action_import_other_file, debug methods, etc.] ...

    def import_excel_file(self):
        """Import principal"""
        self.ensure_one()
        if not self.import_file:
            raise UserError(_("Aucun fichier fourni!"))

        try:
            data = base64.b64decode(self.import_file)
        except Exception as e:
            _logger.exception("Base64 decode failed: %s", e)
            raise UserError(_("Erreur décodage base64 du fichier : %s") % str(e))

        try:
            xls_obj = pd.ExcelFile(io.BytesIO(data))
        except Exception:
            try:
                xls_obj = pd.ExcelFile(io.BytesIO(data), engine='openpyxl')
            except Exception as e:
                _logger.exception("Could not open Excel: %s", e)
                raise UserError(_("Impossible d'ouvrir le fichier Excel. Format invalide ou dépendances manquantes."))

        # remove old data
        try:
            with self.env.cr.savepoint():
                self.lots_ids.unlink()
                self.task_ids.unlink()
        except Exception as e:
            _logger.warning("Could not unlink existing tasks/lots: %s", e)

        # ensure tax 19% exists and assign to project
        tax19 = self._ensure_tva_19()
        if tax19 and tax19 not in self.tax_ids:
            self.tax_ids = [(4, tax19.id)]

        sheet_errors = []
        processed = []

        for sheet in xls_obj.sheet_names:
            try:
                try:
                    df_quick = pd.read_excel(xls_obj, sheet_name=sheet, header=None, nrows=8, dtype=object)
                    if df_quick.dropna(how='all').shape[0] < 2:
                        _logger.info("Skipping sheet (probably empty/cover): %s", sheet)
                        continue
                except Exception:
                    pass

                self._process_sheet_table_only(xls_obj, sheet, suffix='', source='primary')
                processed.append(sheet)
            except Exception as e:
                tb = traceback.format_exc()
                _logger.exception("Error processing sheet %s: %s", sheet, tb)
                sheet_errors.append((sheet, str(e)))
                continue

        if sheet_errors:
            msg = "Feuilles traitées: %s\nFeuilles en erreur:\n" % (", ".join(processed) or "aucune")
            for s, msg_err in sheet_errors:
                msg += "- %s : %s\n" % (s, msg_err)
            _logger.warning("Import partial: %s", msg)
            raise UserError(_("Import partiel terminé. Résumé:\n%s") % msg)

        return True

    def action_import_other_file(self):
        """Import logments (append)"""
        self.ensure_one()
        if not self.import_other_file:
            raise UserError(_("Aucun fichier logments fourni!"))

        try:
            data = base64.b64decode(self.import_other_file)
        except Exception as e:
            _logger.exception("Base64 decode failed (secondary): %s", e)
            raise UserError(_("Erreur décodage base64 du fichier logments : %s") % str(e))

        try:
            xls_obj = pd.ExcelFile(io.BytesIO(data))
        except Exception:
            try:
                xls_obj = pd.ExcelFile(io.BytesIO(data), engine='openpyxl')
            except Exception as e:
                _logger.exception("Could not open secondary Excel: %s", e)
                raise UserError(
                    _("Impossible d'ouvrir le fichier Excel logments. Format invalide ou dépendances manquantes."))

        # ensure tax 9% exists and assign to project for secondary file
        tax9 = self._ensure_tva_9()
        if tax9 and tax9 not in self.tax_ids_2:
            self.tax_ids_2 = [(4, tax9.id)]

        sheet_errors = []
        processed = []
        for sheet in xls_obj.sheet_names:
            try:
                try:
                    df_quick = pd.read_excel(xls_obj, sheet_name=sheet, header=None, nrows=8, dtype=object)
                    if df_quick.dropna(how='all').shape[0] < 2:
                        _logger.info("Skipping secondary sheet (empty/cover): %s", sheet)
                        continue
                except Exception:
                    pass

                self._process_sheet_table_only(xls_obj, sheet, suffix=' (logments)', source='secondary')
                processed.append(sheet)
            except Exception as e:
                tb = traceback.format_exc()
                _logger.exception("Error processing secondary sheet %s: %s", sheet, tb)
                sheet_errors.append((sheet, str(e)))
                continue

        if sheet_errors:
            msg = "Feuilles traitées: %s\nFeuilles en erreur:\n" % (", ".join(processed) or "aucune")
            for s, msg_err in sheet_errors:
                msg += "- %s : %s\n" % (s, msg_err)
            _logger.warning("Secondary import partial: %s", msg)
            raise UserError(_("Import partiel terminé (logments). Résumé:\n%s") % msg)

        return True

    # debug preview
    def debug_excel_preview(self):
        self.ensure_one()
        if not self.import_file:
            raise UserError(_("Aucun fichier fourni!"))

        try:
            data = base64.b64decode(self.import_file)
        except Exception as e:
            raise UserError(_("Erreur décodage base64: %s") % str(e))
        try:
            xls = pd.ExcelFile(io.BytesIO(data))
        except Exception:
            try:
                xls = pd.ExcelFile(io.BytesIO(data), engine='openpyxl')
            except Exception as e:
                _logger.exception("debug_excel_preview open failed: %s", e)
                raise UserError(_("Impossible d'ouvrir le fichier pour preview: %s. Voir logs.") % str(e))

        out = "Feuilles trouvées: %s\n\n" % ", ".join(xls.sheet_names)
        for sheet in xls.sheet_names:
            try:
                df = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=30, dtype=object)
                out += "=== %s ===\n" % sheet
                for idx, row in df.iterrows():
                    cells = [str(x)[:400].replace("\n", " ") for x in row.fillna('').tolist()]
                    out += " | ".join(cells) + "\n"
                out += "\n"
            except Exception as e:
                out += "=== %s ===\nERROR reading preview: %s\n\n" % (sheet, str(e))
        raise UserError(out)

    # ----------------------------
    # HTML Table Rendering (primary)
    # ----------------------------
    @api.depends('task_ids', 'lots_ids', 'task_ids.total_price', 'lots_ids.task_ids.total_price')
    def _compute_table_html(self):
        for project in self:
            lots_file1 = project.lots_ids.filtered(lambda l: l.import_source == 'primary')
            html = """
            <style>
                .table-container-primary {
                    max-height: 600px;
                    overflow-y: auto;
                    overflow-x: auto;
                    border-radius: 12px;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
                }
                .modern-table {
                    border-collapse: separate;
                    border-spacing: 0;
                    width: 100%;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .modern-table thead {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    position: sticky;
                    top: 0;
                    z-index: 10;
                }
                .modern-table thead th {
                    color: #ffffff;
                    font-weight: 600;
                    font-size: 12px;
                    padding: 14px 12px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    border: none;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    position: sticky;
                    top: 0;
                    z-index: 10;
                }
                .modern-table tbody tr {
                    transition: all 0.2s ease;
                }
                .modern-table tbody tr:nth-child(even) {
                    background-color: #f8fafc;
                }
                .modern-table tbody tr:nth-child(odd) {
                    background-color: #ffffff;
                }
                .modern-table tbody tr:hover {
                    background: linear-gradient(135deg, rgba(102, 126, 234, 0.08) 0%, rgba(118, 75, 162, 0.08) 100%);
                    transform: scale(1.001);
                }
                .modern-table tbody td {
                    padding: 12px;
                    font-size: 13px;
                    color: #334155;
                    border-bottom: 1px solid #e2e8f0;
                }
                .lot-header {
                    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%) !important;
                    color: #ffffff !important;
                    font-weight: 700;
                    font-size: 14px;
                }
                .lot-header td {
                    color: #ffffff !important;
                    padding: 14px 12px !important;
                }
                .subtotal-row {
                    background: linear-gradient(135deg, #1e293b 0%, #334155 100%) !important;
                }
                .subtotal-row td {
                    color: #ffffff !important;
                    font-weight: 700;
                    padding: 14px 12px !important;
                }
                .category-row {
                    background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(5, 150, 105, 0.15) 100%) !important;
                    border-left: 4px solid #10b981;
                }
                .category-row td {
                    color: #065f46 !important;
                    font-weight: 600;
                }
                .title-row {
                    background: linear-gradient(135deg, rgba(251, 191, 36, 0.15) 0%, rgba(245, 158, 11, 0.15) 100%) !important;
                    border-left: 4px solid #f59e0b;
                }
                .title-row td {
                    font-weight: 600;
                }
                .parent-task-row {
                    background-color: #f1f5f9 !important;
                }
                .parent-task-row td {
                    font-weight: 600;
                    color: #1e293b;
                }
            </style>
            <div class="table-container-primary">
            <table class="modern-table">
                <thead>
                    <tr>
                        <th style="width:5%;">N°</th>
                        <th style="width:55%;">DESIGNATION DES OUVRAGES</th>
                        <th style="width:5%;">U</th>
                        <th style="width:10%;text-align:right;">QUANTITES</th>
                        <th style="width:10%;text-align:right;">PRIX UNITAIRES</th>
                        <th style="width:15%;text-align:right;">MONTANT</th>
                    </tr>
                </thead>
                <tbody>"""

            for lot in lots_file1:
                html += f'<tr class="lot-header"><td colspan="6">{lot.name or ""}</td></tr>'

                # Get all tasks for this lot (both parent and child tasks)
                all_tasks = lot.task_ids.filtered(lambda t: t.import_source == 'primary').sorted(
                    key=lambda r: r.sequence)

                # Find top-level tasks (no parent)
                top_tasks = all_tasks.filtered(lambda t: not t.parent_id)

                for task in top_tasks:
                    html += self._render_task_with_children(task, all_tasks)

                # ADD THE LOT S_TOTAL AFTER ALL TASKS
                html += f'''
                <tr class="subtotal-row">
                    <td colspan="5" style="text-align:right;">SOUS TOTAL {lot.name or ""}</td>
                    <td style="text-align:right;">{self._format_number(lot.s_total, 2)}</td>
                </tr>
                '''

            html += "</tbody></table></div>"
            project.table_html = html

    def _render_task_with_children(self, task, all_tasks, level=0):
        """Recursively render a task and its children for primary table"""
        html = ""
        no = task.no or ''
        # Use unit field instead of unit_name
        unit_display = task.unit.name if task.unit else ''

        # Handle different task types
        if getattr(task, 'is_title', False):
            if getattr(task, 'is_category', False):
                html += f'<tr class="category-row"><td colspan="6">{task.name or ""}</td></tr>'
            else:
                html += f'<tr class="title-row"><td colspan="6">{task.name or ""}</td></tr>'
            return html

        if no == 's/total':
            html += f'<tr class="subtotal-row"><td colspan="2">{task.name or ""}</td><td style="text-align:right;" colspan="4">{self._format_number(task.total_price, 2)}</td></tr>'
            return html

        # Calculate padding for child tasks
        padding_left = level * 20

        # Get child tasks
        child_tasks = all_tasks.filtered(lambda t: t.parent_id == task).sorted(key=lambda r: r.sequence)

        # If this task has children, it's a parent task
        if child_tasks:
            # Render parent task (show total but no quantity/price details)
            html += f'<tr class="parent-task-row">'
            html += f'<td>{no}</td>'
            html += f'<td style="padding-left:{padding_left}px;">{task.name or ""}</td>'
            html += f'<td>{unit_display}</td>'
            html += f'<td style="text-align:right;"></td>'
            html += f'<td style="text-align:right;"></td>'
            html += f'<td style="text-align:right;"></td>'
            html += '</tr>'

            # Render all child tasks
            for child in child_tasks:
                html += self._render_task_with_children(child, all_tasks, level + 1)
        else:
            # This is a leaf task (no children) - show full details
            html += f'<tr>'
            html += f'<td>{no}</td>'
            html += f'<td style="padding-left:{padding_left}px;">{task.name or ""}</td>'
            html += f'<td>{unit_display}</td>'
            html += f'<td style="text-align:right;">{self._format_number(task.quantity, 3)}</td>'
            html += f'<td style="text-align:right;">{self._format_number(task.unit_price, 3)}</td>'
            html += f'<td style="text-align:right;">{self._format_number(task.total_price, 3)}</td>'
            html += '</tr>'

        return html

    # ----------------------------
    # HTML Table Rendering (secondary)
    # ----------------------------
    @api.depends('task_ids', 'lots_ids', 'task_ids.total_price', 'lots_ids.task_ids.total_price')
    def _compute_other_table_html(self):
        for project in self:
            lots = project.lots_ids.filtered(lambda l: l.import_source == 'secondary').sorted(key=lambda r: r.sequence)
            html = """
            <style>
                .table-container-secondary {
                    max-height: 600px;
                    overflow-y: auto;
                    overflow-x: auto;
                    border-radius: 12px;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
                }
                .modern-table-secondary {
                    border-collapse: separate;
                    border-spacing: 0;
                    width: 100%;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .modern-table-secondary thead {
                    background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                    position: sticky;
                    top: 0;
                    z-index: 10;
                }
                .modern-table-secondary thead th {
                    color: #ffffff;
                    font-weight: 600;
                    font-size: 12px;
                    padding: 14px 12px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    border: none;
                    background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                    position: sticky;
                    top: 0;
                    z-index: 10;
                }
                .modern-table-secondary tbody tr {
                    transition: all 0.2s ease;
                }
                .modern-table-secondary tbody tr:nth-child(even) {
                    background-color: #f0fdf4;
                }
                .modern-table-secondary tbody tr:nth-child(odd) {
                    background-color: #ffffff;
                }
                .modern-table-secondary tbody tr:hover {
                    background: linear-gradient(135deg, rgba(17, 153, 142, 0.08) 0%, rgba(56, 239, 125, 0.08) 100%);
                    transform: scale(1.001);
                }
                .modern-table-secondary tbody td {
                    padding: 12px;
                    font-size: 13px;
                    color: #334155;
                    border-bottom: 1px solid #d1fae5;
                }
                .lot-header-secondary {
                    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%) !important;
                    color: #ffffff !important;
                    font-weight: 700;
                    font-size: 14px;
                }
                .lot-header-secondary td {
                    color: #ffffff !important;
                    padding: 14px 12px !important;
                }
                .subtotal-row-secondary {
                    background: linear-gradient(135deg, #1e293b 0%, #334155 100%) !important;
                }
                .subtotal-row-secondary td {
                    color: #ffffff !important;
                    font-weight: 700;
                    padding: 14px 12px !important;
                }
                .category-row-secondary {
                    background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(5, 150, 105, 0.15) 100%) !important;
                    border-left: 4px solid #10b981;
                }
                .category-row-secondary td {
                    color: #065f46 !important;
                    font-weight: 600;
                }
                .title-row-secondary {
                    background: linear-gradient(135deg, rgba(251, 191, 36, 0.15) 0%, rgba(245, 158, 11, 0.15) 100%) !important;
                    border-left: 4px solid #f59e0b;
                }
                .title-row-secondary td {
                    font-weight: 600;
                }
                .parent-task-row-secondary {
                    background-color: #ecfdf5 !important;
                }
                .parent-task-row-secondary td {
                    font-weight: 600;
                    color: #1e293b;
                }
                .empty-message {
                    text-align: center;
                    padding: 30px;
                    color: #64748b;
                    font-style: italic;
                }
            </style>
            <div class="table-container-secondary">
            <table class="modern-table-secondary">
                <thead>
                    <tr>
                        <th style="width:5%;">N°</th>
                        <th style="width:55%;">DESIGNATION DES OUVRAGES</th>
                        <th style="width:5%;">U</th>
                        <th style="width:10%;text-align:right;">QUANTITES</th>
                        <th style="width:10%;text-align:right;">PRIX UNITAIRES</th>
                        <th style="width:15%;text-align:right;">MONTANT</th>
                    </tr>
                </thead>
                <tbody>"""

            if not lots:
                html += '<tr><td colspan="6" class="empty-message">Aucun lot logments importé</td></tr>'

            for lot in lots:
                html += f'<tr class="lot-header-secondary"><td colspan="6">{lot.name or ""}</td></tr>'

                # Get all tasks for this lot
                all_tasks = lot.task_ids.filtered(lambda t: t.import_source == 'secondary').sorted(
                    key=lambda r: r.sequence)

                # Find top-level tasks (no parent)
                top_tasks = all_tasks.filtered(lambda t: not t.parent_id)

                for task in top_tasks:
                    html += self._render_task_with_children_secondary(task, all_tasks)

                # ADD THE LOT S_TOTAL AFTER ALL TASKS
                html += f'''
                <tr class="subtotal-row-secondary">
                    <td colspan="5" style="text-align:right;">SOUS TOTAL {lot.name or ""}</td>
                    <td style="text-align:right;">{self._format_number(lot.s_total, 2)}</td>
                </tr>
                '''

            html += "</tbody></table></div>"
            project.other_table_html = html

    def _render_task_with_children_secondary(self, task, all_tasks, level=0):
        """Recursively render a task and its children for secondary table"""
        html = ""
        no = task.no or ''
        # Use unit field instead of unit_name
        unit_display = task.unit.name if task.unit else ''

        # Handle different task types
        if getattr(task, 'is_title', False):
            if getattr(task, 'is_category', False):
                html += f'<tr class="category-row-secondary"><td colspan="6">{task.name or ""}</td></tr>'
            else:
                html += f'<tr class="title-row-secondary"><td colspan="6">{task.name or ""}</td></tr>'
            return html

        if no == 's/total':
            html += f'<tr class="subtotal-row-secondary"><td colspan="2">{task.name or ""}</td><td style="text-align:right;" colspan="4">{self._format_number(task.total_price, 2)}</td></tr>'
            return html

        # Calculate padding for child tasks
        padding_left = level * 20

        # Get child tasks
        child_tasks = all_tasks.filtered(lambda t: t.parent_id == task).sorted(key=lambda r: r.sequence)

        # If this task has children, it's a parent task
        if child_tasks:
            # Render parent task (show total but no quantity/price details)
            html += f'<tr class="parent-task-row-secondary">'
            html += f'<td>{no}</td>'
            html += f'<td style="padding-left:{padding_left}px;">{task.name or ""}</td>'
            html += f'<td>{unit_display}</td>'
            html += f'<td style="text-align:right;"></td>'
            html += f'<td style="text-align:right;"></td>'
            html += f'<td style="text-align:right;"></td>'
            html += '</tr>'

            # Render all child tasks
            for child in child_tasks:
                html += self._render_task_with_children_secondary(child, all_tasks, level + 1)
        else:
            # This is a leaf task (no children) - show full details
            html += f'<tr>'
            html += f'<td>{no}</td>'
            html += f'<td style="padding-left:{padding_left}px;">{task.name or ""}</td>'
            html += f'<td>{unit_display}</td>'
            html += f'<td style="text-align:right;">{self._format_number(task.quantity, 3)}</td>'
            html += f'<td style="text-align:right;">{self._format_number(task.unit_price, 3)}</td>'
            html += f'<td style="text-align:right;">{self._format_number(task.total_price, 3)}</td>'
            html += '</tr>'

        return html

    def debug_check_subtasks(self):
        """Debug method to check subtask relationships"""
        self.ensure_one()
        tasks = self.task_ids.sorted('sequence')

        debug_info = f"Total tasks: {len(tasks)}\n\n"

        for task in tasks:
            debug_info += f"Task: {task.no or 'No Code'} - '{task.name}'\n"
            debug_info += f"  Parent: {task.parent_id.name if task.parent_id else 'None'}\n"
            debug_info += f"  Children: {len(task.child_ids)}\n"
            debug_info += f"  Lot: {task.lot_id.name if task.lot_id else 'None'}\n"
            debug_info += f"  Import Source: {task.import_source}\n"
            debug_info += "  ---\n"

        raise UserError(debug_info)

    def debug_subtotal_detection(self):
        """Debug method to check subtotal detection"""
        self.ensure_one()
        if not self.import_file:
            raise UserError(_("No file provided!"))

        try:
            data = base64.b64decode(self.import_file)
            xls_obj = pd.ExcelFile(io.BytesIO(data))
        except Exception as e:
            raise UserError(_("Error reading file: %s") % str(e))

        debug_info = "Subtotal Detection Debug:\n\n"

        for sheet in xls_obj.sheet_names:
            debug_info += f"=== Sheet: {sheet} ===\n"
            try:
                df = pd.read_excel(xls_obj, sheet_name=sheet, header=None, dtype=object)
                for idx, row in df.iterrows():
                    clean_row = [self._clean_cell(c) for c in row.tolist()]
                    if any(clean_row):  # Skip empty rows
                        row_text = ' '.join([str(c) for c in clean_row if c])
                        contains_subtotal = self._contains_subtotal_keyword(clean_row)
                        debug_info += f"Row {idx}: {contains_subtotal} - {row_text[:100]}...\n"
            except Exception as e:
                debug_info += f"Error reading sheet: {str(e)}\n"

        raise UserError(debug_info)

    def debug_total_calculation(self):
        """Debug method to check total calculation"""
        self.ensure_one()
        primary_lots = self.lots_ids.filtered(lambda l: l.import_source == 'primary')
        secondary_lots = self.lots_ids.filtered(lambda l: l.import_source == 'secondary')

        debug_info = f"Project: {self.name}\n"
        debug_info += f"Total Price (computed): {self.total_price}\n"
        debug_info += f"Total Price 2 (computed): {self.total_price_2}\n\n"

        debug_info += "Primary lots breakdown:\n"
        for lot in primary_lots:
            debug_info += f"- {lot.name}: {lot.s_total}\n"
        debug_info += f"Sum of primary lots: {sum(l.s_total or 0.0 for l in primary_lots)}\n\n"

        debug_info += "Secondary lots breakdown:\n"
        for lot in secondary_lots:
            debug_info += f"- {lot.name}: {lot.s_total}\n"
        debug_info += f"Sum of secondary lots: {sum(l.s_total or 0.0 for l in secondary_lots)}\n"

        raise UserError(debug_info)

    def action_draft(self):
        self.state = 'draft'

    def action_confirm(self):
        self.state = 'confirmed'

    def action_done(self):
        self.state = 'done'

    def action_cancel(self):
        self.state = 'cancelled'

    # ---------- Progress Calculation Methods ----------
    def _compute_situation_count(self):
        """Compute the number of situations for this project"""
        for project in self:
            situations = self.env['situation'].search([('project_id', '=', project.id)])
            project.situation_count = len(situations)
            project.paid_situation_count = len(situations.filtered(lambda s: s.state == 'paid'))

    @api.depends('total_intern')
    def _compute_payment_stats(self):
        """Compute total paid and remaining amounts"""
        for project in self:
            situations = self.env['situation'].search([('project_id', '=', project.id)])
            total_paid = sum(s.paid_amount for s in situations if hasattr(s, 'paid_amount'))
            project.total_paid = total_paid
            project.total_remaining = (project.total_intern or 0.0) - total_paid

    @api.depends('total_intern', 'total_paid')
    def _compute_progress(self):
        """Compute project progress percentage"""
        for project in self:
            if project.total_intern and project.total_intern > 0:
                project.progress = min(100.0, (project.total_paid / project.total_intern) * 100)
            else:
                project.progress = 0.0

    def action_view_situations(self):
        """Open situations linked to this project"""
        self.ensure_one()
        return {
            'name': _('Situations'),
            'type': 'ir.actions.act_window',
            'res_model': 'situation',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
            'target': 'current',
        }


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _visible_menu_ids(self, debug=False):
        visible = super()._visible_menu_ids(debug=debug)
        # hide the “Projets S-T” menu for finance group
        if self.env.user.has_group('custom_groups.group_financiere'):
            menu = self.env.ref('custom_project.custom_project_root_menu', raise_if_not_found=False)
            if menu:
                visible = visible - {menu.id}
        return visible
