from odoo import models, fields, api


class PrintOrdreVirementWizard(models.TransientModel):
    _name = 'commercial.print.ordre.virement.wizard'
    _description = "Imprimer un ordre de virement"

    paiement_id = fields.Many2one('commercial.paiement', string="Paiement", required=True)
    type_virement = fields.Selection([
        ('cache_tranche', 'Cache / Tranche'),
        ('apport_declare', 'Apport personnel déclaré'),
        ('apport_non_declare', 'Apport personnel non déclaré'),
        ('cb', 'Crédit bancaire'),
    ], string="Type de virement", required=True)
    echeance_id = fields.Many2one(
        'commercial.echeance', string="Échéance",
        domain="[('paiement_id', '=', paiement_id)]")
    echeance_apport_declare_id = fields.Many2one(
        'commercial.echeance.apport.declare', string="Échéance AP déclaré",
        domain="[('paiement_id', '=', paiement_id)]")
    echeance_apport_non_declare_id = fields.Many2one(
        'commercial.echeance.apport', string="Échéance AP non déclaré",
        domain="[('paiement_id', '=', paiement_id)]")
    echeance_cb_id = fields.Many2one(
        'commercial.echeance', string="Échéance crédit bancaire",
        domain="[('paiement_id', '=', paiement_id)]")

    def action_print(self):
        self.ensure_one()
        echeance = self.get_echeance()
        if echeance:
            return self.env.ref(
                'commercial.action_report_ordre_virement'
            ).report_action(self)

    def get_echeance(self):
        """Retourne l'échéance sélectionnée."""
        self.ensure_one()
        if self.type_virement == 'cache_tranche':
            return self.echeance_id
        if self.type_virement == 'apport_declare':
            return self.echeance_apport_declare_id
        if self.type_virement == 'apport_non_declare':
            return self.echeance_apport_non_declare_id
        return self.echeance_cb_id

    def get_agence(self):
        """Retourne l'agence selon le type."""
        self.ensure_one()
        if self.type_virement == 'cb':
            return self.paiement_id.banque_id.name or ''
        if self.type_virement == 'apport_declare':
            return self.paiement_id.banque_apport_declare_id.name or ''
        return ''

    def get_numero_compte(self):
        """Retourne le N° compte selon le type."""
        self.ensure_one()
        if self.type_virement == 'cb':
            return self.paiement_id.banque_id.compte or ''
        if self.type_virement == 'apport_declare':
            return self.paiement_id.banque_apport_declare_id.compte or ''
        return ''

    def get_adresse(self):
        """Retourne l'adresse selon le type."""
        self.ensure_one()
        if self.type_virement == 'cb':
            return self.paiement_id.banque_id.adresse or ''
        if self.type_virement == 'apport_declare':
            return self.paiement_id.banque_apport_declare_id.adresse or ''
        return ''

    def get_motif(self):
        """Retourne le motif selon le type."""
        self.ensure_one()
        if self.type_virement == 'cache_tranche':
            return "Virement"
        if self.type_virement == 'apport_declare':
            return "Virement Apport personnel déclaré"
        if self.type_virement == 'apport_non_declare':
            return "Virement Apport personnel"
        return "Virement Crédit bancaire"

    def get_montant_en_lettres(self):
        """Retourne le montant de l'échéance en lettres (français)."""
        self.ensure_one()
        echeance = self.get_echeance()
        if not echeance:
            return ''
        montant = echeance.montant
        partie_entiere = int(montant)
        partie_decimale = round((montant - partie_entiere) * 100)
        resultat = self._nombre_en_lettres(partie_entiere) + ' Dinars'
        if partie_decimale > 0:
            resultat += ' et ' + self._nombre_en_lettres(partie_decimale) + ' Centimes'
        return resultat

    @staticmethod
    def _nombre_en_lettres(n):
        if n == 0:
            return 'zéro'

        unites = [
            '', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept',
            'huit', 'neuf', 'dix', 'onze', 'douze', 'treize', 'quatorze',
            'quinze', 'seize', 'dix-sept', 'dix-huit', 'dix-neuf',
        ]
        dizaines = ['', '', 'vingt', 'trente', 'quarante', 'cinquante', 'soixante']

        def _moins_de_100(x):
            if x < 20:
                return unites[x]
            if x < 70:
                d, u = x // 10, x % 10
                if u == 0:
                    return dizaines[d]
                if u == 1:
                    return dizaines[d] + ' et un'
                return dizaines[d] + '-' + unites[u]
            if x < 80:
                u = x - 60
                if u == 11:
                    return 'soixante et onze'
                return 'soixante-' + unites[u]
            # 80-99
            u = x - 80
            if u == 0:
                return 'quatre-vingts'
            if u < 20:
                return 'quatre-vingt-' + unites[u]
            return 'quatre-vingt-' + _moins_de_100(u)

        def _moins_de_1000(x):
            if x < 100:
                return _moins_de_100(x)
            c, r = x // 100, x % 100
            if c == 1:
                prefix = 'cent'
            elif r == 0:
                return unites[c] + ' cents'
            else:
                prefix = unites[c] + ' cent'
            if r == 0:
                return prefix
            return prefix + ' ' + _moins_de_100(r)

        parts = []
        if n >= 1000000000:
            milliards = n // 1000000000
            n = n % 1000000000
            if milliards == 1:
                parts.append('un milliard')
            else:
                parts.append(_moins_de_1000(milliards) + ' milliards')
        if n >= 1000000:
            millions = n // 1000000
            n = n % 1000000
            if millions == 1:
                parts.append('un million')
            else:
                parts.append(_moins_de_1000(millions) + ' millions')
        if n >= 1000:
            milliers = n // 1000
            n = n % 1000
            if milliers == 1:
                parts.append('mille')
            else:
                parts.append(_moins_de_1000(milliers) + ' mille')
        if n > 0:
            parts.append(_moins_de_1000(n))
        return ' '.join(parts)
