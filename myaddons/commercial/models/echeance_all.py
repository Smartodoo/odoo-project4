from odoo import models, fields, tools
from odoo.exceptions import UserError


class CommercialEcheanceAll(models.Model):
    _name = 'commercial.echeance.all'
    _description = "Toutes les échéances"
    _auto = False
    _order = 'date desc'

    type_echeance = fields.Selection([
        ('cache', 'Cache'),
        ('tranche', 'Tranche'),
        ('cb', 'Crédit Bancaire'),
        ('ap_non_declare', 'AP non déclaré'),
        ('ap_declare', 'AP déclaré'),
        ('coprop', 'Copropriété'),
    ], string="Type", readonly=True)
    paiement_id = fields.Many2one('commercial.paiement', string="Paiement", readonly=True)
    client_id = fields.Many2one('res.partner', string="Client", readonly=True)
    lot_id = fields.Many2one('commercial.lot', string="Lot", readonly=True)
    projet_id = fields.Many2one('commercial.projet', string="Projet", readonly=True)
    numero = fields.Integer(string="N°", readonly=True)
    date = fields.Date(string="Date", readonly=True)
    date_encaissement = fields.Date(string="Date encaissement", readonly=True)
    pourcentage = fields.Float(string="%", readonly=True)
    montant = fields.Float(string="Montant", readonly=True)
    etat = fields.Selection([
        ('brouillon', 'Brouillon'),
        ('paye', 'Payé'),
        ('annule', 'Annulé'),
    ], string="État", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    e.id AS id,
                    p.type_paiement AS type_echeance,
                    e.paiement_id,
                    p.client_id,
                    p.lot_id,
                    l.projet_id,
                    e.numero,
                    e.date,
                    e.date_encaissement,
                    e.pourcentage,
                    e.montant,
                    e.etat
                FROM commercial_echeance e
                JOIN commercial_paiement p ON e.paiement_id = p.id
                LEFT JOIN commercial_lot l ON p.lot_id = l.id

                UNION ALL

                SELECT
                    1000000 + ea.id AS id,
                    'ap_non_declare' AS type_echeance,
                    ea.paiement_id,
                    p.client_id,
                    p.lot_id,
                    l.projet_id,
                    ea.numero,
                    ea.date,
                    ea.date_encaissement,
                    ea.pourcentage,
                    ea.montant,
                    ea.etat
                FROM commercial_echeance_apport ea
                JOIN commercial_paiement p ON ea.paiement_id = p.id
                LEFT JOIN commercial_lot l ON p.lot_id = l.id

                UNION ALL

                SELECT
                    2000000 + ead.id AS id,
                    'ap_declare' AS type_echeance,
                    ead.paiement_id,
                    p.client_id,
                    p.lot_id,
                    l.projet_id,
                    ead.numero,
                    ead.date,
                    ead.date_encaissement,
                    ead.pourcentage,
                    ead.montant,
                    ead.etat
                FROM commercial_echeance_apport_declare ead
                JOIN commercial_paiement p ON ead.paiement_id = p.id
                LEFT JOIN commercial_lot l ON p.lot_id = l.id

                UNION ALL

                SELECT
                    3000000 + ec.id AS id,
                    'coprop' AS type_echeance,
                    ec.paiement_id,
                    p.client_id,
                    p.lot_id,
                    l.projet_id,
                    ec.numero,
                    ec.date,
                    NULL AS date_encaissement,
                    NULL AS pourcentage,
                    ec.montant,
                    ec.etat
                FROM commercial_echeance_coprop ec
                JOIN commercial_paiement p ON ec.paiement_id = p.id
                LEFT JOIN commercial_lot l ON p.lot_id = l.id
            )
        """ % self._table)

    def action_preview_report_multi(self):
        """Prévisualiser le rapport pour plusieurs enregistrements sélectionnés"""
        if not self:
            raise UserError("Veuillez sélectionner au moins un enregistrement.")
        ids_str = ','.join(str(rec.id) for rec in self)
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/commercial.report_recap_paiement_template/%s' % ids_str,
            'target': 'new',
        }
