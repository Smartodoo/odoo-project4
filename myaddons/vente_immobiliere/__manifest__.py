# -*- coding: utf-8 -*-
{
    'name': 'Vente Immobiliere',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Gestion de vente et location immobiliere',
    'description': """
        Module de gestion de vente et location immobiliere.
        - Hierarchie de localisation: Wilaya / Daira / Commune
        - Structure de projet: Projet / Bloc / Etage / Appartement
        - Workflow de reservation avec integration sale.order
    """,
    'author': 'Projet Innovation',
    'depends': ['base', 'sale', 'account', 'mail', 'contacts', 'custom_project'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/wilaya_data.xml',
        'views/wilaya_views.xml',
        'views/projet_immobilier_views.xml',
        'views/bloc_views.xml',
        'views/etage_views.xml',
        'views/appartement_views.xml',
        'views/reservation_views.xml',
        'views/menu.xml',
        'report/reservation_report.xml',
        'report/reservation_template.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
