from odoo import models, fields, api


class PrintListeLotsWizard(models.TransientModel):
    _name = 'commercial.print.liste.lots.wizard'
    _description = "Imprimer liste des lots"

    projet_id = fields.Many2one('commercial.projet', string="Projet", required=True)
    bloc_id = fields.Many2one(
        'commercial.bloc', string="Bloc",
        domain="[('projet_id', '=', projet_id)]")
    etage_id = fields.Many2one(
        'commercial.etage', string="Étage",
        domain="[('bloc_id', '=', bloc_id)]")
    categorie_id = fields.Many2one(
        'commercial.categorie', string="Catégorie",
        domain="[('etage_id', '=', etage_id)]")
    state = fields.Selection([
        ('disponible', 'Disponible'),
        ('en_option', 'Pré-réservé'),
        ('reserve', 'Réservé'),
        ('loue', 'Loué'),
        ('vendu', 'Vendu'),
    ], string="État")

    @api.onchange('bloc_id')
    def _onchange_bloc_id(self):
        if self.etage_id and self.etage_id.bloc_id != self.bloc_id:
            self.etage_id = False
            self.categorie_id = False

    @api.onchange('etage_id')
    def _onchange_etage_id(self):
        if self.categorie_id and self.categorie_id.etage_id != self.etage_id:
            self.categorie_id = False

    def _get_filtered_lots(self):
        self.ensure_one()
        domain = [('projet_id', '=', self.projet_id.id)]
        if self.bloc_id:
            domain.append(('bloc_id', '=', self.bloc_id.id))
        if self.etage_id:
            domain.append(('etage_id', '=', self.etage_id.id))
        if self.categorie_id:
            domain.append(('categorie_id', '=', self.categorie_id.id))
        if self.state:
            domain.append(('state', '=', self.state))
        return self.env['commercial.lot'].search(domain)

    def action_print(self):
        self.ensure_one()
        lots = self._get_filtered_lots()
        return self.env.ref(
            'commercial.action_report_liste_lots'
        ).report_action(lots)
