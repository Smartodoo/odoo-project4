from odoo import api, fields, models


class SuiviG50(models.Model):
    _name = 'administration.suivi.g50'
    _description = 'Suivi G50'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'annee desc, mois desc'

    date_depot = fields.Date(string='Date dépôt', tracking=True)
    mois = fields.Selection([
        ('01', 'Janvier'),
        ('02', 'Février'),
        ('03', 'Mars'),
        ('04', 'Avril'),
        ('05', 'Mai'),
        ('06', 'Juin'),
        ('07', 'Juillet'),
        ('08', 'Août'),
        ('09', 'Septembre'),
        ('10', 'Octobre'),
        ('11', 'Novembre'),
        ('12', 'Décembre'),
    ], string='Mois', required=True, tracking=True)
    annee = fields.Selection(
        selection='_get_year_selection',
        string='Année', required=True, tracking=True,
    )
    montant = fields.Float(string='Montant', tracking=True)
    state = fields.Selection([
        ('non_paye', 'Non payé'),
        ('paye', 'Payé'),
    ], string='État', default='non_paye', required=True, tracking=True)
    date_paiement = fields.Date(string='Date de paiement', tracking=True)
    methode_paiement = fields.Selection([
        ('espece', 'Espèce'),
        ('cheque', 'Chèque'),
    ], string='Méthode de paiement', tracking=True)
    numero_cheque = fields.Char(string='Numéro de chèque', tracking=True)
    piece_jointe_ids = fields.Many2many('ir.attachment', string='Pièces jointes')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)

    @api.model
    def _get_year_selection(self):
        current_year = fields.Date.today().year
        return [(str(y), str(y)) for y in range(current_year - 5, current_year + 6)]