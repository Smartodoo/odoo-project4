# -*- encoding: utf-8 -*-
{
    'name': 'administration',
    'version': '1.0',
    'category': 'administration/Management',
    'sequence': 10,
    'description': """
     Module d'administration pour la gestion et le suivi des aspects juridiques et financiers de l'entreprise.
    """,
    'author': 'naoual smartodoo',
    'company': 'smartodoo',
    'website': '',
    'depends': ['base', 'contacts'],

    'data': [
        'security/ir.model.access.csv',
        'views/juridique_view.xml',
        'views/credit_bancaire_view.xml',
        'views/suivi_g50_view.xml',
        'views/administration_menu.xml',
        'data/ir_cron.xml',

    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    'icon': 'administration/static/description/img.png',
}
