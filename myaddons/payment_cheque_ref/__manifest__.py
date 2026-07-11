{
    'name': 'Paiement Chèque - Référence',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': "Ajoute le mode Chèque sur les journaux banque avec saisie de la référence du chèque.",
    'description': """
        Étend le wizard d'enregistrement de paiement (account.payment.register) :
        - Sur un journal de type banque, le mode de paiement propose Manuel + Chèque.
        - Quand Chèque est sélectionné, un champ « Référence du chèque » apparaît.
        - La référence est propagée sur l'account.payment créé.

        Indépendant du module beton_caisse — utilise un code de méthode distinct.
    """,
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['account', 'caisse2', 'sale_management', 'purchase'],
    'data': [
        'data/payment_method_data.xml',
        'views/account_payment_views.xml',
        'views/sale_purchase_views.xml',
        'views/account_menu_order.xml',
        'views/account_move_views.xml',
        'views/account_move_search_views.xml',
        'views/report_invoice_inherit.xml',
    ],
    'installable': True,
    'application': False,
    'post_init_hook': 'post_init_hook',
}
