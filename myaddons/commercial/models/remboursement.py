from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CommercialRemboursement(models.Model):
    _name = 'commercial.remboursement'
    _description = 'Remboursement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string="Référence", readonly=True, default='Nouveau', copy=False)
    versement_id = fields.Many2one('commercial.versement', string="Versement", required=True,
                                   ondelete='cascade',
                                   domain="[('state', 'in', ['confirme', 'partiellement_rembourse'])]", tracking=True)
    client_id = fields.Many2one('res.partner', string="Client",
                                related='versement_id.client_id', store=True, readonly=True)
    lot_id = fields.Many2one('commercial.lot', string="Lot",
                             related='versement_id.lot_id', store=True, readonly=True)
    montant_verse = fields.Float(string="Montant déjà versé",
                                 related='versement_id.montant', readonly=True)
    montant_restant = fields.Float(string="Montant restant",
                                   related='versement_id.montant_restant', readonly=True)
    montant_rembourse = fields.Float(string="Montant à rembourser", tracking=True)
    date = fields.Date(string="Date", default=fields.Date.context_today, tracking=True)
    note = fields.Text(string="Note")
    caisse_entry_id = fields.Many2one('caisse.entry', string="Encaissement caisse", readonly=True, copy=False)
    state = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('confirme', 'Confirmé'),
    ], string="État", default='brouillon', tracking=True)

    def get_client_id_document(self):
        """Retourne le premier document d'identité valide du client."""
        self.ensure_one()
        valid_types = ('cni', 'permis_conduire', 'passeport', 'carte_militaire')
        for doc in self.client_id.document_ids:
            if doc.type_document in valid_types:
                return doc
        return False

    def get_type_document_label(self, doc):
        """Retourne le libellé du type de document."""
        labels = {
            'cni': "Carte d'identité nationale",
            'permis_conduire': "Permis de conduire",
            'passeport': "Passeport",
            'carte_militaire': "Carte militaire",
        }
        return labels.get(doc.type_document, '')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code('commercial.remboursement') or 'Nouveau'
        return super().create(vals_list)

    @api.constrains('montant_rembourse', 'versement_id')
    def _check_montant_rembourse(self):
        for rec in self:
            if rec.montant_rembourse <= 0:
                raise ValidationError("Le montant à rembourser doit être supérieur à 0.")
            montant_restant = rec.versement_id.montant_restant
            if rec.montant_rembourse > montant_restant:
                raise ValidationError(
                    "Le montant à rembourser (%.2f) ne peut pas dépasser le montant restant (%.2f)."
                    % (rec.montant_rembourse, montant_restant))

    def _get_cashbox(self):
        """Retourne la caisse selon le mode de paiement du versement lié."""
        self.ensure_one()
        versement = self.versement_id
        if versement.mode_paiement in ('cheque', 'virement'):
            return self.env.ref('caisse2.caisse_verte')
        return self.env.ref('caisse2.caisse_espece_commerciale')

    def action_confirmer(self):
        for rec in self:
            rec.state = 'confirme'
            # Soustraire le montant remboursé de la caisse
            cashbox = rec._get_cashbox()
            cashbox.sudo().total_amount -= rec.montant_rembourse
            if rec.versement_id:
                versement = rec.versement_id
                total_rembourse = sum(
                    r.montant_rembourse for r in versement.remboursement_ids if r.state == 'confirme'
                )
                if total_rembourse >= versement.montant:
                    versement.state = 'totalement_rembourse'
                    # Si tous les versements du lot sont totalement remboursés, remettre en pré-réservation
                    if versement.lot_id:
                        lot = versement.lot_id
                        all_versements = lot.versement_ids.filtered(lambda v: v.active)
                        all_rembourses = all(v.state == 'totalement_rembourse' for v in all_versements)
                        if all_rembourses:
                            lot.write({'state': 'en_option'})
                else:
                    versement.state = 'partiellement_rembourse'