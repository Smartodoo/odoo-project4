from odoo import models, fields, api


class PrintSituationWizard(models.TransientModel):
    _name = 'commercial.print.situation.wizard'
    _description = "Imprimer situation financière"

    partner_id = fields.Many2one('res.partner', string="Contact")
    lot_id = fields.Many2one(
        'commercial.lot', string="Lot", required=True,
        domain="[('id', 'in', available_lot_ids)]")
    available_lot_ids = fields.Many2many(
        'commercial.lot', compute='_compute_available_lot_ids')
    paiement_id = fields.Many2one(
        'commercial.paiement', string="Paiement", required=True,
        domain="[('lot_id', '=', lot_id), ('client_id', '=', partner_id)]")
    type_impression = fields.Selection([
        ('situation_detaillee', 'Situation financière détaillée'),
        ('situation_declarees', 'Situation financière déclarées'),
        ('situation_reservation', 'Situation de réservation'),
        ('dossier_avec', 'Dossier client avec transactions'),
        ('dossier_sans', 'Dossier client sans transactions'),
    ], string="Type d'impression", required=True, default='situation_detaillee')

    @api.depends('partner_id')
    def _compute_available_lot_ids(self):
        for rec in self:
            if rec.partner_id:
                rec.available_lot_ids = rec.partner_id.commercial_lot_ids
            else:
                rec.available_lot_ids = self.env['commercial.lot']

    @api.onchange('lot_id')
    def _onchange_lot_id(self):
        if self.lot_id and self.partner_id:
            paiement = self.env['commercial.paiement'].search([
                ('lot_id', '=', self.lot_id.id),
                ('client_id', '=', self.partner_id.id),
            ], limit=1)
            self.paiement_id = paiement.id if paiement else False

    def action_print(self):
        self.ensure_one()
        report_map = {
            'situation_detaillee': 'commercial.action_report_situation_financiere',
            'situation_declarees': 'commercial.action_report_situation_declarees',
            'situation_reservation': 'commercial.action_report_situation_reservation',
            'dossier_avec': 'commercial.action_report_dossier_client_avec',
            'dossier_sans': 'commercial.action_report_dossier_client_sans',
        }
        ref = report_map.get(self.type_impression)
        if ref:
            return self.env.ref(ref).report_action(self)

    def get_echeances_declarees(self):
        """Retourne les échéances CB payées (transactions déclarées)."""
        self.ensure_one()
        return self.paiement_id.echeance_ids.filtered(
            lambda e: e.etat == 'paye'
        ).sorted(key=lambda e: e.date_encaissement or e.date or fields.Date.today(), reverse=True)

    def get_echeances_non_declarees(self):
        """Retourne les échéances AP payées (transactions non déclarées)."""
        self.ensure_one()
        return self.paiement_id.echeance_apport_ids.filtered(
            lambda e: e.etat == 'paye'
        ).sorted(key=lambda e: e.date_encaissement or e.date or fields.Date.today(), reverse=True)

    def get_all_transactions(self):
        """Retourne toutes les échéances payées (CB + AP) pour le dossier client."""
        self.ensure_one()
        p = self.paiement_id
        result = []
        for e in p.echeance_ids.filtered(lambda e: e.etat == 'paye'):
            result.append({
                'mode': 'VIREMENT',
                'date': e.date_encaissement or e.date,
                'montant': e.montant,
                'nature': 'Encaissement CB',
                'observation': self.get_observation_cb(e),
            })
        for e in p.echeance_apport_ids.filtered(lambda e: e.etat == 'paye'):
            result.append({
                'mode': 'ESPECES',
                'date': e.date_encaissement or e.date,
                'montant': e.montant,
                'nature': 'Encaissement AP',
                'observation': self.get_observation_ap(e),
            })
        result.sort(key=lambda r: r['date'] or fields.Date.today(), reverse=True)
        return result

    def get_montant_encaisse(self):
        """Montant encaissé = payé CB + payé AP."""
        self.ensure_one()
        p = self.paiement_id
        return p.montant_paye_cb + p.montant_deja_paye_apport

    def get_reste_encaisser(self):
        """Reste à encaisser = reste CB + reste AP."""
        self.ensure_one()
        p = self.paiement_id
        return p.reste_cb + p.reste_apport

    def get_type_lot(self):
        """Retourne le type du lot (Habitat/Local Commercial)."""
        self.ensure_one()
        lot = self.paiement_id.lot_id
        if lot.tva and '19' in str(lot.tva):
            return "Local Commercial"
        return "Habitat"

    @staticmethod
    def get_observation_cb(echeance):
        """Génère l'observation pour une échéance CB."""
        ordinal = "1ERE" if echeance.numero == 1 else "%dEME" % echeance.numero
        pct = int(echeance.pourcentage)
        return "DEBLOCAGE DES %d%% DE LA %s TRANCHE DU MONTANT ACCORDE" % (pct, ordinal)

    @staticmethod
    def get_observation_ap(echeance):
        """Génère l'observation pour une échéance AP."""
        ordinal = "1ERE" if echeance.numero == 1 else "%dEME" % echeance.numero
        pct = int(echeance.pourcentage)
        return "APPORT PERSONNEL %d%% - %s TRANCHE" % (pct, ordinal)
