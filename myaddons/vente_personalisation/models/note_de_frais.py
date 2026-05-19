from odoo import models, api, _, fields
from odoo.exceptions import UserError


class HrExpense(models.Model):
    _inherit = "hr.expense"

    @api.ondelete(at_uninstall=False)
    def _unlink_except_posted_or_approved(self):
        for expense in self:
            if self.env.user.has_group('base.group_system'):  # Only admin users can force delete
                expense._unlink_related_documents()
                continue  # Continue to next record

            # Prevent deletion if expense is 'approved' or 'done'
            if expense.state in {'done', 'approved'}:
                raise UserError(_('You cannot delete a posted or approved expense.'))

    def _unlink_related_documents(self):
        """Supprime en toute sécurité les paiements et écritures comptables liés."""
        for expense in self:
            # 1️⃣ Trouver les paiements liés
            payments = self.env['account.payment'].sudo().search([('ref', '=', expense.name)])

            # 2️⃣ Trouver les écritures comptables liées
            moves = self.env['account.move'].sudo().search(
                [('ref', '=', expense.name)]
            )
            print('moves', moves)
            print('payments', payments)

            # 🔹 Vérifier et annuler les écritures comptables
            for move in moves:
                if move.state != 'draft':
                    move.button_draft()  # Passer en brouillon avant suppression

                # 🔹 Supprimer les lignes de rapprochement bancaire
                for line in move.line_ids:
                    if line.reconciled:
                        line.remove_move_reconcile()

                move.unlink()  # Supprimer après sécurisation

            attachments = self.env['ir.attachment'].sudo().search([
                ('res_model', '=', 'hr.expense'), ('res_id', '=', expense.id)
            ])
            if attachments:
                attachments.unlink()
