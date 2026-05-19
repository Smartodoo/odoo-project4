from odoo import models, fields


class DocumentDeleteWizard(models.TransientModel):
    _name = 'commercial.document.delete.wizard'
    _description = 'Confirmation de suppression du document'

    document_id = fields.Many2one('commercial.document.partner', string="Document")
    document_name = fields.Char(related='document_id.fichier_name', string="Fichier")
    document_type = fields.Selection(related='document_id.type_document', string="Type")

    def action_delete(self):
        """Supprime le document et ferme le dialogue."""
        self.ensure_one()
        if self.document_id:
            self.document_id.unlink()
        return {'type': 'ir.actions.act_window_close'}
