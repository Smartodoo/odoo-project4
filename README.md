# projet4 - Odoo 20 (CE)

Addons custom du projet 4, en **Odoo 20 Community**.
Migré depuis Odoo 17 le 2026-11-10 (données migrées 17 → 18 → 19 → 20 via OpenUpgrade + scripts maison).
La dernière version Odoo 17 est conservée dans la branche **`odoo17`**.

## Informations du projet

- **Version Odoo :** 20 (Community)
- **Instance serveur :** `projet420` (PostgreSQL 18, port 5433)
- **Bases :**
  - `base1` — port HTTP 8120 / websocket 7120
  - `base2` (Auberge) — port HTTP 8121 / websocket 7121 — https://auberge.smartodoo.com
- **Utilisateur base de données :** `projet420`
- **Mot de passe maître :** voir `admin_passwd` dans `.odoo/odoo-base1.conf` / `.odoo/odoo-base2.conf` (non versionné)

## Modules (`myaddons/`)

| Module | Rôle |
|---|---|
| `hotel_management` | Auberge : chambres, lits, réservations, paiements, ménage, travaux, site de réservation |
| `rental_management` | Gestion locative immobilière |
| `custom_project` | Projets / sous-traitants / situations |
| `Purchase_custom` | Achats et versements fournisseurs |
| `HR_customization` | Personnalisations contacts / RH |
| `sinistre` | Sinistres et parc automobile |
| `vente_personalisation` | Personnalisations ventes et rapports |
| `custom_groups`, `hide_menu_user`, `purchase_report_preview_ldtech` | Utilitaires |
| `sh_entmate_theme` | Thème backend |

## Développement

Le code cible **Odoo 20** : vues `list` (plus `tree`), `<chatter/>`, templates kanban `card`,
`t-out` (plus `t-esc`), `ir.access.csv`, groupes via `res.groups.privilege`, OWL 3 (`this.` dans
les templates), états de paiement `paid` / `reconciled`.
