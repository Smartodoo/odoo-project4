import base64

from odoo import http
from odoo.http import request, Response


class DocumentPreviewController(http.Controller):

    @http.route('/commercial/document/preview/<int:doc_id>',
                type='http', auth='user')
    def preview_document(self, doc_id, download=None, **kwargs):
        """Sert le fichier (authentifié) pour PDF/images."""
        doc = request.env['commercial.document.partner'].browse(doc_id)
        if not doc.exists():
            return Response('Document introuvable', status=404)

        attachment = request.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'commercial.document.partner'),
            ('res_id', '=', doc_id),
            ('res_field', '=', 'fichier'),
        ], limit=1)

        if not attachment or not attachment.datas:
            return Response('Fichier introuvable', status=404)

        return self._serve_file(doc, attachment, download)

    @http.route('/commercial/document/public/<int:doc_id>',
                type='http', auth='public')
    def public_document(self, doc_id, token=None, **kwargs):
        """Sert le fichier (public avec token) pour Office Online."""
        if not token:
            return Response('Token manquant', status=403)

        doc = request.env['commercial.document.partner'].sudo().browse(doc_id)
        if not doc.exists() or doc.access_token != token:
            return Response('Accès refusé', status=403)

        attachment = request.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'commercial.document.partner'),
            ('res_id', '=', doc_id),
            ('res_field', '=', 'fichier'),
        ], limit=1)

        if not attachment or not attachment.datas:
            return Response('Fichier introuvable', status=404)

        return self._serve_file(doc, attachment, download=False)

    def _serve_file(self, doc, attachment, download=None):
        """Retourne le fichier avec les bons headers HTTP."""
        file_data = base64.b64decode(attachment.datas)
        filename = doc.fichier_name or 'document'
        ftype = (doc.fichier_type or '').upper()

        content_types = {
            'PDF': 'application/pdf',
            'PNG': 'image/png',
            'JPG': 'image/jpeg',
            'JPEG': 'image/jpeg',
            'GIF': 'image/gif',
            'BMP': 'image/bmp',
            'WEBP': 'image/webp',
            'XLSX': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'XLS': 'application/vnd.ms-excel',
            'DOCX': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'DOC': 'application/msword',
        }
        content_type = content_types.get(ftype, 'application/octet-stream')
        disposition = 'attachment' if download else 'inline'

        return Response(
            file_data,
            headers={
                'Content-Type': content_type,
                'Content-Disposition': '%s; filename="%s"' % (disposition, filename),
                'Content-Length': str(len(file_data)),
            },
        )
