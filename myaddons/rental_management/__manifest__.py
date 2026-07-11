# -*- coding: utf-8 -*-
{
    'name': '🏠 Gestion Locative Immobilière Pro',
    'version': '2.0.0',
    'category': 'Real Estate',
    'summary': 'Gestion complète et intelligente des appartements et locations',
    'description': """
        ╔═══════════════════════════════════════════════════════════════╗
        ║  MODULE PRO DE GESTION LOCATIVE — VERSION ULTRA              ║
        ╠═══════════════════════════════════════════════════════════════╣
        ║                                                               ║
        ║  🏢 APPARTEMENTS                                              ║
        ║     • Types : Studio, F1, F2, F3, F4                         ║
        ║     • Localisation GPS + Carte interactive                   ║
        ║     • Score de confort algorithmique (0-100)                 ║
        ║     • Tarification intelligente (4 périodes + saisonnier)    ║
        ║                                                               ║
        ║  📋 CONTRATS DE LOCATION                                      ║
        ║     • Workflow 5 états : Brouillon → Confirmé → En Cours    ║
        ║       → Bientôt Terminé → Terminé                            ║
        ║     • Calcul prix optimal automatique                        ║
        ║     • Caution intelligente (fidélité + plafond)              ║
        ║     • Anti-chevauchement automatique                         ║
        ║                                                               ║
        ║  💳 CAISSE & PAIEMENTS                                        ║
        ║     • 6 méthodes de paiement                                 ║
        ║     • 5 types : Loyer, Caution, Service, Pénalité, Remb.     ║
        ║     • Relances automatiques par email                        ║
        ║                                                               ║
        ║  📋 ÉTATS DES LIEUX                                           ║
        ║     • Checklist numérique complète                           ║
        ║     • Photos avant/après + Dégâts                            ║
        ║     • Signatures électroniques (locataire + inspecteur)      ║
        ║     • Gestion des contestations                              ║
        ║                                                               ║
        ║  🔧 MAINTENANCE                                               ║
        ║     • 9 catégories d'intervention                            ║
        ║     • 4 niveaux de priorité                                  ║
        ║     • Affectation technicien + Prestataire externe           ║
        ║     • Satisfaction locataire post-intervention               ║
        ║                                                               ║
        ║  👤 PROFIL LOCATAIRE (CRM intégré)                            ║
        ║     • Système de fidélité : Bronze → Platine                 ║
        ║     • Scoring de risque : Faible → Élevé                     ║
        ║     • Documents (CIN) + Contact d'urgence                    ║
        ║                                                               ║
        ║  📊 TABLEAU DE BORD                                           ║
        ║     • KPI en temps réel (Glassmorphism)                      ║
        ║     • Revenus : Jour / Semaine / Mois / Année                ║
        ║     • Alertes : Expirantes, Impayés, Maintenances            ║
        ║                                                               ║
        ║  📈 PRÉVISIONS INTELLIGENTES                                  ║
        ║     • Analyse historique 3 ans                               ║
        ║     • Variance + Tendance (Hausse/Stable/Baisse)             ║
        ║                                                               ║
        ║  🌐 PORTAIL CLIENT                                            ║
        ║     • Formulaire public responsive premium                   ║
        ║     • Sélection visuelle des appartements                    ║
        ║     • Anti-doublon + Vérification disponibilité              ║
        ║                                                               ║
        ║  📄 RAPPORTS PDF                                              ║
        ║     • Contrat de location juridique                          ║
        ║     • Quittance de loyer fiscale                             ║
        ║                                                               ║
        ║  🤖 AUTOMATISATIONS                                           ║
        ║     • Cron quotidien (états, alertes, relances)              ║
        ║     • Emails automatiques (expiration, paiement, maint.)     ║
        ║                                                               ║
        ╚═══════════════════════════════════════════════════════════════╝
    """,
    'author': 'Stage Pro — Développement Expert',
    'website': 'https://www.immobilier-pro.dz',
    'depends': ['base', 'mail', 'website', 'portal'],
    'data': [
        # Sécurité
        'security/ir.model.access.csv',
        'security/rental_security.xml',

        # Données de base
        'data/ir_sequence_data.xml',
        #'data/cron.xml',
        'data/mail_template.xml',
        'data/demo_data.xml',

        # Vues
        'views/property_views.xml',        # ← CORRIGÉ
        'views/client_views.xml',
        'views/rental_views.xml',
        'views/payment_views.xml',
        'views/maintenance_views.xml',
        'views/inspection_views.xml',
        'views/seasonal_views.xml',
        'views/service_views.xml',
        #'views/forecast_views.xml',
        'views/dashboard_views.xml',
        'views/public_templates.xml',
        'views/report_templates.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'rental_management/static/src/scss/_design_tokens.scss',
            'rental_management/static/src/scss/main.scss',
            'rental_management/static/src/js/dashboard_chart.js',
        ],
        'web.assets_frontend': [
            'rental_management/static/src/css/custom_style.css',
        ],
   },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
}