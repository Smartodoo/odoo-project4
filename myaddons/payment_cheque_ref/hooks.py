CHEQUE_REF_CODE = 'cheque_ref'


def sync_cheque_ref_method_lines(env):
    """Garantit que la méthode 'cheque_ref' est rattachée uniquement aux
    journaux de type 'bank' :
      - Supprime les lignes erronées (méthode sur journal non-bank)
      - Crée les lignes manquantes sur les journaux bank
    """
    Line = env['account.payment.method.line']

    # 1) Lignes mal rattachées (pas sur un journal bank)
    wrong = Line.search([
        ('payment_method_id.code', '=', CHEQUE_REF_CODE),
        ('journal_id.type', '!=', 'bank'),
    ])
    if wrong:
        wrong.sudo().unlink()

    # 2) Crée les lignes manquantes sur tous les journaux bank
    methods = env['account.payment.method'].search([
        ('code', '=', CHEQUE_REF_CODE),
    ])
    bank_journals = env['account.journal'].search([
        ('type', '=', 'bank'),
        ('company_id', 'in', env.companies.ids),
    ])
    for method in methods:
        for journal in bank_journals:
            existing = Line.search([
                ('payment_method_id', '=', method.id),
                ('journal_id', '=', journal.id),
            ], limit=1)
            if not existing:
                Line.sudo().create({
                    'name': method.name,
                    'payment_method_id': method.id,
                    'journal_id': journal.id,
                })


def post_init_hook(env):
    sync_cheque_ref_method_lines(env)
