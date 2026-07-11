from odoo import models, fields, api


class PrintCopropWizard(models.TransientModel):
    _name = 'commercial.print.coprop.wizard'
    _description = "Imprimer reçu copropriété"

    paiement_id = fields.Many2one('commercial.paiement', string="Paiement", required=True)
    echeance_coprop_id = fields.Many2one(
        'commercial.echeance.coprop', string="Échéance Copropriété",
        domain="[('paiement_id', '=', paiement_id), ('etat', '=', 'paye')]",
        required=True)

    def action_print(self):
        self.ensure_one()
        return self.env.ref(
            'commercial.action_report_coprop'
        ).report_action(self)

    def get_qualite_label(self):
        """Retourne le libellé de la qualité avec de/d' adapté."""
        self.ensure_one()
        user = self.env.user
        if not user.qualite:
            return "de Commercial"
        label = dict(self.env['res.users']._fields['qualite'].selection).get(user.qualite, '')
        if not label:
            return "de Commercial"
        if label[0].upper() in ('A', 'E', 'I', 'O', 'U', 'É', 'È', 'Ê'):
            return "d'%s" % label
        return "de %s" % label
