# -*- coding: utf-8 -*-
{
    'name': "Achat_personalisation",
    'summary': "",
    'description': """
    """,

    'author': "Meziani",
    'website': "",
    'category': 'Achat',
    'version': '0.1',
    'depends': ['base', 'sale', 'hr', 'purchase', 'account', 'contacts', 'custom_project', 'fleet', 'mail'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/multicompany_rules.xml',
        'views/purchase_order.xml',
        'views/distribution_montant.xml',
        'views/versement.xml',
        'data/sequence_data.xml',
        'views/nettoyage_situation.xml',
        'views/nettoyage_resources.xml',
        'views/situation_brise_roche.xml',
        'data/paperformat.xml',
        'report/purchase_supplier_template.xml',
        'report/report_versement.xml',
        'report/report_situation_brise_roche.xml',
        'report/report_nettoyage_chauffeur_camion.xml',
        'report/report_nettoyage_sous_traitant.xml',
        'report/report_brise_roche_list.xml',
    ],
    'installable': True,
    'application': False,
}
