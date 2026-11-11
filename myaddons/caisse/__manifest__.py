{
    'name': "Caisse",
    'summary': "Caisse de l'auberge : ouverture, fermeture, entrées, sorties, dépenses, écart",
    'description': """
Gestion de caisse (cahier des charges §9)
=========================================
  * Ouverture de caisse avec fond de caisse, fermeture avec comptage
  * Paiements clients en espèces rattachés automatiquement à la caisse ouverte
  * Entrées, sorties, dépenses et transferts justifiés (pièce jointe)
  * Journal de caisse, total encaissé / dépensé, solde, paiements par mode, écart
  * Impression de l'état de caisse
""",
    'author': "SmartOdoo",
    'website': "https://smartodoo.com",
    'category': 'Accounting',
    'version': '20.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['hotel_management'],
    'data': [
        'security/caisse_security.xml',
        'security/ir.access.csv',
        'data/caisse_data.xml',
        'report/caisse_report.xml',
        'views/caisse_views.xml',
    ],
    'application': True,
    'installable': True,
}
