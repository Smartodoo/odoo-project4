# -*- coding: utf-8 -*-
{
    'name': "vente_personalisation",
    'summary': "",
    'description': """
    """,

    'author': "tech",
    'website': "",
    'category': 'Uncategorized',
    'version': '0.1',
    'depends': ['base', 'sale', 'hr', 'contacts'],
    'data': [
        # 'security/ir.model.access.csv',
        'views/sale_order_views_inherit.xml',
        'views/product_template_inherit.xml',
        'report/sale_order_proformat_template.xml',
        'report/sale_order_template.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'vente_personalisation/static/src/css/mon_style.css',
        ],
    },
    'installable': True,
    'application': False,
}
