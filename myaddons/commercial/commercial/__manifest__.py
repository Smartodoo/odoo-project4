{
    'name': 'Commercial',
    'version': '17.0.1.0.0',
    'category': 'Real Estate',
    'summary': 'Gestion de projets immobiliers',
    'description': """
        Module de gestion commerciale des projets immobiliers.
        - Fiche projet complète
        - Gestion des blocs
        - Gestion des lots
        - Gestion des étages
    """,
    'author': 'Custom',
    'depends': ['base', 'contacts', 'mail', 'calendar', 'crm', 'sale', 'purchase', 'account', 'hr', 'custom_project', 'HR_customization'],
    'data': [
        'security/ir.model.access.csv',
        'data/type_projet_data.xml',
        'views/projet_views.xml',
        'views/bloc_views.xml',
        'views/lot_views.xml',
        'views/etage_views.xml',
        'views/categorie_views.xml',
        'views/commercial_menu.xml',
        'views/contact_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'icon': 'commercial/static/description/img.png',
}
