{
    'name': "Auberge",
    'summary': "Gestion complète d'un hôtel : chambres, réservations, tableau de bord",
    'description': """
Gestion d'auberge (PMS) — cahier des charges complet
=====================================================
  * Chambres, lits, types, équipements, tarifs saisonniers et tarifs clients
  * Réservations (chambre ou lit), planning graphique, check-in / check-out
  * Consommations et services, remises, facturation automatique
  * Paiements (acompte, partiel, total, remboursement) — caisse : module « caisse »
  * Ménage (à nettoyer, en nettoyage, nettoyée, contrôlée, à réparer), travaux
  * Personnel (intégration des applications Employés, Présences, Congés)
  * Tableau de bord, statistiques, rapports PDF, alertes
  * Site web de réservation en ligne
""",
    'author': "SmartOdoo",
    'website': "https://smartodoo.com",
    'category': 'Services/Hotel',
    'version': '20.0.2.0.0',
    'license': 'LGPL-3',
    'depends': ['mail', 'web', 'contacts', 'website', 'portal', 'account',
                'hr', 'hr_attendance', 'hr_holidays'],
    'data': [
        'security/hotel_security.xml',
        'data/hotel_sequence.xml',
        'data/hotel_data.xml',
        'data/mail_template_data.xml',
        'data/website_data.xml',
        'data/hotel_payment_data.xml',
        'data/hotel_product_data.xml',
        'report/hotel_reports.xml',
        'views/hotel_amenity_views.xml',
        'views/hotel_room_type_views.xml',
        'views/hotel_room_views.xml',
        'views/hotel_bed_views.xml',
        'views/hotel_rate_season_views.xml',
        'views/hotel_reservation_mail_wizard_views.xml',
        'views/hotel_reservation_payment_wizard_views.xml',
        'views/account_move_views.xml',
        'views/hotel_reservation_views.xml',
        'views/res_partner_views.xml',
        'views/hotel_operations_views.xml',
        'views/hotel_kanban_views.xml',
        'views/hotel_dashboard_views.xml',
        'views/hotel_report_views.xml',
        'views/hotel_menus.xml',
        'views/website_hotel_home_settings_views.xml',
        'views/website_hotel_templates.xml',
        'views/website_hotel_homepage.xml',
        'views/website_hotel_layout.xml',
        'views/website_hotel_menus.xml',
        'views/portal_hotel_templates.xml',
        'security/ir.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'hotel_management/static/src/scss/hotel_statusbar.scss',
            'hotel_management/static/src/room/hotel_room.scss',
            'hotel_management/static/src/scss/hotel_kanban.scss',
            'hotel_management/static/src/dashboard/hotel_dashboard.scss',
            'hotel_management/static/src/dashboard/hotel_dashboard.js',
            'hotel_management/static/src/dashboard/hotel_dashboard.xml',
            'hotel_management/static/src/planning/hotel_planning.scss',
            'hotel_management/static/src/planning/hotel_planning.js',
            'hotel_management/static/src/planning/hotel_planning.xml',
        ],
        'web.assets_frontend': [
            'hotel_management/static/src/website/hotel_website.scss',
            'hotel_management/static/src/website/hotel_home.js',
        ],
    },
    'application': True,
    'installable': True,
}
