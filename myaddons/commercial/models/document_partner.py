import uuid

from odoo import models, fields, api


class CommercialDocumentPartner(models.Model):
    _name = 'commercial.document.partner'
    _description = 'Document du contact'
    _order = 'create_date desc'

    partner_id = fields.Many2one(
        'res.partner', string="Contact", required=True, ondelete='cascade')
    type_document = fields.Selection([
        ('aucun', 'Aucun'),
        ('cni', "Carte d'identité nationale"),
        ('permis_conduire', 'Permis de conduire'),
        ('passeport', 'Passeport'),
        ('carte_militaire', 'Carte militaire'),
    ], string="Type Doc.", default='aucun')
    numero_document = fields.Char(string="N° doc.")
    date_delivrance = fields.Date(string="Délivré le")
    delivre_par = fields.Char(string="Délivré par")
    document_valide = fields.Boolean(string="Document validé")
    fichier = fields.Binary(string="Fichier", attachment=True)
    fichier_name = fields.Char(string="Nom du fichier")
    fichier_type = fields.Char(
        string="Type fichier", compute='_compute_fichier_type', store=True)
    access_token = fields.Char(string="Token d'accès", copy=False)

    @api.depends('fichier_name')
    def _compute_fichier_type(self):
        for rec in self:
            if rec.fichier_name:
                ext = rec.fichier_name.rsplit('.', 1)[-1].upper() if '.' in rec.fichier_name else ''
                rec.fichier_type = ext
            else:
                rec.fichier_type = False

    def action_save_and_close(self):
        return {'type': 'ir.actions.act_window_close'}

    def _generate_access_token(self):
        """Génère un token d'accès temporaire pour le fichier."""
        self.ensure_one()
        token = str(uuid.uuid4())
        self.sudo().write({'access_token': token})
        return token

    def action_download(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/commercial/document/preview/%s?download=true' % self.id,
            'target': 'new',
        }

    def action_view_file(self):
        self.ensure_one()
        ftype = (self.fichier_type or '').upper()

        # DOCX/XLSX : téléchargement direct
        if ftype in ('DOCX', 'DOC', 'XLSX', 'XLS'):
            return {
                'type': 'ir.actions.act_url',
                'url': '/commercial/document/preview/%s?download=true' % self.id,
                'target': 'new',
            }

        # PDF/Images : utiliser le file_viewer natif d'Odoo
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'fichier'),
        ], limit=1)
        if not attachment:
            return False
        return {
            'type': 'ir.actions.client',
            'tag': 'commercial.document_preview',
            'target': 'new',
            'params': {
                'attachment_id': attachment.id,
                'filename': self.fichier_name or 'Document',
                'mimetype': attachment.mimetype or 'application/pdf',
            },
        }

    def action_confirm_delete(self):
        """Ouvre un dialogue de confirmation avant suppression."""
        self.ensure_one()
        wizard = self.env['commercial.document.delete.wizard'].create({
            'document_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirmer la suppression',
            'res_model': 'commercial.document.delete.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
