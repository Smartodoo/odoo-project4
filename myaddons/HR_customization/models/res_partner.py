from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    vat_company = fields.Char(string="N.I.F")
    nis = fields.Char(string='N.I.S')
    ai = fields.Char(string='Article d\'imposition')
    company_registry = fields.Char(string="R.C")



class ResPartnerExt(models.Model):
    _inherit = 'res.partner'

    contact_type = fields.Selection(
        [('SUPPLIER', 'Fournisseur'), ('CLIENT', 'Client'), ('SUBCONTRACTOR', 'Sous-traitant')], string='Contact Type',
        default='CLIENT')
    vat = fields.Char(string='N.I.F', index=True,
                      help="The Tax Identification Number. Complete it if the contact is subjected to government taxes. Used in some legal statements.")
    nis = fields.Char(string='N.I.S')
    ai = fields.Char(string='Article d\'imposition')
    company_registry = fields.Char(string='R.C')

    # document_count = fields.Integer(string="Documents", compute="_compute_document_count")
    #
    # def _compute_document_count(self):
    #     Document = self.env['document.page']
    #     for partner in self:
    #         partner.document_count = Document.search_count([
    #             ('partner_id', '=', partner.id)
    #         ])

    # def open_file(self):
    #     self.ensure_one()
    #     # On prépare juste le contexte et le domaine pour les fichiers
    #     return {
    #         'context': {
    #             'default_partner_id': self.id,
    #             'filter_from_partner': True,  # flag pour filtrage si nécessaire
    #         },
    #         'domain': [('partner_id', '=', self.id)],
    #     }

    # def open_document(self):
    #     self.ensure_one()
    #
    #     # On appelle open_file pour récupérer le contexte et le domaine filtré
    #     file_data = self.open_file()
    #
    #     return {
    #         'name': 'Documents',
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'document.page',
    #         'views': [(False, 'kanban'), (False, 'tree'), (False, 'form')],
    #         'view_mode': 'kanban,tree,form',
    #         'target': 'current',
    #         'context': dict(self.env.context, **file_data['context']),  # merge contexte
    #         'domain': [('partner_id', '=', [self.id])],
    #     }



