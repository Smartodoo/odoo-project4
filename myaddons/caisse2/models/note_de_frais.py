from odoo import models, api, _
import logging

_logger = logging.getLogger(__name__)


class HrExpenseSheet(models.Model):
    _inherit = 'paiement.situation'

    def test_log1(self):
        print("✅ Bouton Confirmer Paiement cliqué :", self.situation_id.name)
        caisse_expense_model = self.env['caisse.expense']
        cashbox_model = self.env['cashbox']
        for rec in self:
            print("Traitement de la situation :", rec.situation_id.name)
            # Find the specific cashbox named "Caisse Espèce"
            caisse_record = cashbox_model.sudo().search([
                ('responsible_ids', '=', rec.user_id.id),
                ('name', '=', 'Caisse Espèce')
            ], order='id desc', limit=1)

            if not caisse_record:
                _logger.warning("⚠️ Aucune caisse nommée 'Caisse Espèce' trouvée pour l'utilisateur %s",
                                rec.user_id.name)
                continue  # skip to next record if not found
            paid_before = sum(
                p.amount_paid for p in rec.situation_id.paiement_situation_ids if p.id != rec.id and p.status == 'paid')
            amount_verse = paid_before + rec.amount_paid
            caisse_expense_model.create({
                'name': self.env['ir.sequence'].next_by_code('caisse.expense') or '/',
                'description': rec.reference,
                'amount': rec.situation_id.net_amount,
                'employee_id': rec.user_id.employee_id.id if rec.user_id.employee_id else False,
                'user_id': rec.user_id.id,
                'cashbox_id': caisse_record.id,
                'company_id': rec.company_id.id,
                'situation_id': rec.situation_id.id,
                'amount_paid': rec.amount_paid,
                'amount_verse': amount_verse,
                'amount_residual': rec.situation_id.net_amount - amount_verse,
                'state': 'draft',
            })
            print("Caisse expense créée pour :", rec.situation_id.name)
            _logger.info("💰 Caisse expense créée pour %s dans %s", rec.situation_id.name, caisse_record.name)
            self.situation_id.poush_notification()
            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': _('Notification envoyée 🎉'),
                    'type': 'rainbow_man',
                }
            }
        return True

    # def _do_approve(self):
    #     res = super()._do_approve()
    #
    #     caisse_expense_model = self.env['caisse.expense']
    #     for situation in self:
    #         _logger.info("✅ Création automatique de caisse.expense pour la situation : %s", sheet.name)
    #         caisse = self.sudo().env['cashbox']
    #         is_caisse = caisse.sudo().search([])
    #         caisse_ids = caisse.sudo().search([('responsible_ids', '=', self.user_id.id)], order='id desc')
    #
    #         if caisse_ids:
    #             cashbox_id = caisse_ids[0].id
    #         else:
    #             cashbox_id = False  # Ou une autre valeur par défaut
    #
    #         if is_caisse:
    #             caisse_vals = {
    #                 'description': situation.name,
    #                 # 'notes': sheet.note,
    #                 'amount': situation.net_amount,
    #                 'employee_id': situation.user_id.employee_id.id,
    #                 'user_id': situation.user_id.id,
    #                 'cashbox_id': cashbox_id,
    #                 'company_id': situation.company_id.id,
    #                 'note_frais_id': situation.id,
    #                 'state': 'draft',
    #             }
    #         caisse_expense_model.create(caisse_vals)
    #
    #     return res

    # def action_sheet_move_create(self):
    #     res = super().action_sheet_move_create()
    #
    #     for sheet in self:
    #         caisse_expense = self.env['caisse.expense'].search([
    #             ('note_frais_id', '=', sheet.id),
    #             ('state', '!=', 'approuve')
    #         ], limit=1)
    #
    #         if caisse_expense:
    #             _logger.info("✅ Validation automatique de caisse.expense liée à : %s", sheet.name)
    #             caisse_expense.action_to_approuve()
    #
    #     return res
