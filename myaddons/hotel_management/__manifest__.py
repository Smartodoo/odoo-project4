{
    'name': "Auberge",
    'summary': "Gestion complète d'un hôtel : chambres, réservations, tableau de bord",
    'description': """
Gestion Hôtelière (PMS)
=======================
Phase 1 — Cœur :
  * Chambres, types de chambres, équipements
  * Réservations (multi-chambres, check-in / check-out)
  * Tableau de bord : occupation, disponibilité, clients, statistiques
Phases suivantes : site web de réservation, restauration, ménage,
travaux, personnel hôtelier.
""",
    'author': "SmartOdoo",
    'website': "https://smartodoo.com",
    'category': 'Services/Hotel',
    'version': '17.0.1.6.8',
    'license': 'LGPL-3',
    'depends': ['mail', 'web', 'contacts', 'website', 'portal', 'account'],
    'data': [
        'security/hotel_security.xml',
        'security/ir.model.access.csv',
        'security/hotel_website_security.xml',
        'data/hotel_sequence.xml',
        'data/hotel_data.xml',
        'data/mail_template_data.xml',
        'views/hotel_amenity_views.xml',
        'views/hotel_room_type_views.xml',
        'views/hotel_room_views.xml',
        'views/hotel_bed_views.xml',
        'views/hotel_rate_season_views.xml',
        'views/hotel_reservation_views.xml',
        'views/res_partner_views.xml',
        'views/hotel_operations_views.xml',
        'views/hotel_dashboard_views.xml',
        'views/hotel_menus.xml',
        'views/website_hotel_templates.xml',
        'views/website_hotel_menus.xml',
        'views/portal_hotel_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hotel_management/static/src/dashboard/hotel_dashboard.scss',
            'hotel_management/static/src/dashboard/hotel_dashboard.js',
            'hotel_management/static/src/dashboard/hotel_dashboard.xml',
        ],
        'web.assets_frontend': [
            'hotel_management/static/src/website/hotel_website.scss',
        ],
    },
    'application': True,
    'installable': True,
}
