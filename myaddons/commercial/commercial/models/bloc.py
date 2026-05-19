from odoo import models, fields, api


class CommercialBloc(models.Model):
    _name = 'commercial.bloc'
    _description = 'Bloc'

    code = fields.Char(string="Code / N° Bloc", required=True)
    name = fields.Char(string="Nom", compute='_compute_name', store=True)
    projet_id = fields.Many2one(
        'commercial.projet', string="Projet", required=True, ondelete='cascade')
    nbre_etages = fields.Integer(string="Nombre d'étages")
    mezzanine = fields.Integer(string="Nombre de mezzanines")
    nbre_entresols = fields.Integer(string="Nombre d'entresols")
    nbre_soussols = fields.Integer(string="Nombre de sous-sols")
    etage_ids = fields.One2many('commercial.etage', 'bloc_id', string="Étages")

    @api.depends('code')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.code or ''

    @api.onchange('nbre_etages', 'mezzanine', 'nbre_entresols', 'nbre_soussols')
    def _onchange_generate_etages(self):
        for rec in self:
            nbre_etages = rec.nbre_etages or 0
            nbre_mezzanines = rec.mezzanine or 0
            nbre_entresols = rec.nbre_entresols or 0
            nbre_soussols = rec.nbre_soussols or 0

            etages = []
            seq = 0

            # ATTIQUE (dernier étage) — Niv.{mezzanines + nbre_etages}
            if nbre_etages > 0:
                attique_niv = nbre_mezzanines + nbre_etages
                seq += 1
                etages.append((0, 0, {
                    'sequence': seq,
                    'name': 'ATTIQUE',
                    'niveau': "Niv.%d" % attique_niv,
                    'etiquette': 'ATTIQUE',
                    'type_etage': 'terrasse',
                    'numero': attique_niv,
                }))

            # Étages réguliers (du plus haut au plus bas)
            # E{nbre_etages-1} à Niv.{mezzanines+nbre_etages-1} ... E1 à Niv.{mezzanines+1}
            for i in range(nbre_etages - 1, 0, -1):
                seq += 1
                niv = nbre_mezzanines + i
                etages.append((0, 0, {
                    'sequence': seq,
                    'name': "E%d" % i,
                    'niveau': "Niv.%d" % niv,
                    'etiquette': "E%d" % i,
                    'type_etage': 'etage',
                    'numero': niv,
                }))

            # Mezzanines (entre RDC et étages réguliers)
            # Niv.{mezzanines} ... Niv.1
            for i in range(nbre_mezzanines, 0, -1):
                seq += 1
                etages.append((0, 0, {
                    'sequence': seq,
                    'name': "Mezzanine %d" % i if nbre_mezzanines > 1 else "Mezzanine",
                    'niveau': "Niv.%d" % i,
                    'etiquette': "Mezzanine %d" % i if nbre_mezzanines > 1 else "Mezzanine",
                    'type_etage': 'mezzanine',
                    'numero': i,
                }))

            # RDC — Niv.0
            seq += 1
            etages.append((0, 0, {
                'sequence': seq,
                'name': 'RDC',
                'niveau': 'Niv.0',
                'etiquette': 'RDC',
                'type_etage': 'rdc',
                'numero': 0,
            }))

            # Entresols (sous le RDC, au-dessus des sous-sols)
            # E-Sol {nbre_entresols} à Niv.-1 ... E-Sol 1 à Niv.-{nbre_entresols}
            for i in range(1, nbre_entresols + 1):
                seq += 1
                esol_num = nbre_entresols - i + 1
                etages.append((0, 0, {
                    'sequence': seq,
                    'name': "E-Sol %d" % esol_num if nbre_entresols > 1 else "E-Sol",
                    'niveau': "Niv.-%d" % i,
                    'etiquette': "E-Sol %d" % esol_num if nbre_entresols > 1 else "E-Sol",
                    'type_etage': 'entresol',
                    'numero': -i,
                }))

            # Sous-sols (du plus haut au plus profond)
            # S-Sol {nbre_soussols} à Niv.-{entresols+1} ... S-Sol 1 à Niv.-{entresols+soussols}
            for i in range(1, nbre_soussols + 1):
                seq += 1
                niv_neg = nbre_entresols + i
                ssol_num = nbre_soussols - i + 1
                etages.append((0, 0, {
                    'sequence': seq,
                    'name': "S-Sol %d" % ssol_num,
                    'niveau': "Niv.-%d" % niv_neg,
                    'etiquette': "S-Sol %d" % ssol_num,
                    'type_etage': 'sous_sol',
                    'numero': -niv_neg,
                }))

            rec.etage_ids = [(5, 0, 0)] + etages
