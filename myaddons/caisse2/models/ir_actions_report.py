# -*- coding: utf-8 -*-
from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        """
        Override to render caisse2 reports with sudo() to bypass
        multi-company access restrictions on res.company records.
        This allows users to print reports for documents belonging to
        a different company than their current active company.
        """
        report = self._get_report(report_ref)

        # List of caisse2 report names that need sudo access
        caisse2_reports = [
            'caisse2.report_caisse_expense_situation',
            'caisse2.report_caisse_expense_supplier_template',
            'caisse2.report_caisse_expense_global',
            'caisse2.report_caisse_expense_project_template',
            'caisse2.report_project_payments_template',
            'caisse2.report_global_expense_payments_template',
            'caisse2.report_cashbox_transfer_template',
            'caisse2.report_cashbox_recharge_template',
        ]

        if report.report_name in caisse2_reports:
            return super(IrActionsReport, self.sudo())._render_qweb_pdf(
                report_ref, res_ids=res_ids, data=data
            )

        return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
