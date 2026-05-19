#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour mettre à jour les projets dans les enregistrements de caisse existants
"""

import sys
import os

# Ajouter le chemin du serveur Odoo
sys.path.append(os.path.join(os.path.dirname(__file__), 'server'))

import odoo
from odoo import api, SUPERUSER_ID

def update_caisse_projects():
    """Met à jour les projets dans caisse.expense et caisse.expense.globale"""

    # Configuration
    config_file = 'odoo.conf'
    database = 'INV'

    # Charger la configuration
    odoo.tools.config.parse_config(['-c', config_file])

    # Initialiser le registre
    registry = odoo.registry(database)

    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        print("\n" + "="*60)
        print("MISE À JOUR DES PROJETS DANS LES PAIEMENTS CAISSE")
        print("="*60 + "\n")

        # 1. Mettre à jour caisse.expense (Paiements Situations)
        print("1. Mise à jour des Paiements Situations...")
        caisse_expenses = env['caisse.expense'].search([])
        total_expenses = len(caisse_expenses)
        updated_expenses = 0

        for expense in caisse_expenses:
            if expense.situation_id and expense.situation_id.project_id:
                try:
                    # Forcer le recalcul en écrivant dans un champ
                    expense.write({'project_id': expense.situation_id.project_id.id})
                    updated_expenses += 1
                    print(f"   ✓ {expense.name}: Projet '{expense.situation_id.project_id.name}' ajouté")
                except Exception as e:
                    print(f"   ✗ Erreur sur {expense.name}: {str(e)}")

        print(f"\n   Total: {updated_expenses}/{total_expenses} paiements situations mis à jour\n")

        # 2. Mettre à jour caisse.expense.supplier (Paiements Fournisseurs)
        print("2. Mise à jour des Paiements Fournisseurs...")
        supplier_expenses = env['caisse.expense.supplier'].search([])
        total_suppliers = len(supplier_expenses)
        updated_suppliers = 0

        for expense in supplier_expenses:
            if expense.purchase_id and expense.purchase_id.project_id:
                try:
                    # Forcer le recalcul en écrivant dans un champ
                    expense.write({'project_id': expense.purchase_id.project_id.id})
                    updated_suppliers += 1
                    print(f"   ✓ {expense.name}: Projet '{expense.purchase_id.project_id.name}' ajouté")
                except Exception as e:
                    print(f"   ✗ Erreur sur {expense.name}: {str(e)}")

        print(f"\n   Total: {updated_suppliers}/{total_suppliers} paiements fournisseurs mis à jour\n")

        # 3. Recalculer les projets dans caisse.expense.globale
        print("3. Recalcul des Dépenses Globales...")
        globale_expenses = env['caisse.expense.globale'].search([])
        total_globale = len(globale_expenses)
        updated_globale = 0

        for globale in globale_expenses:
            try:
                # Forcer le recalcul des projets
                globale._compute_projects()
                updated_globale += 1
                project_names = ', '.join(globale.project_ids.mapped('name')) if globale.project_ids else 'Aucun'
                print(f"   ✓ {globale.partner_id.name}: Projets [{project_names}]")
            except Exception as e:
                print(f"   ✗ Erreur sur {globale.partner_id.name}: {str(e)}")

        print(f"\n   Total: {updated_globale}/{total_globale} dépenses globales mises à jour\n")

        # Commit des changements
        cr.commit()

        print("="*60)
        print("RÉSUMÉ")
        print("="*60)
        print(f"✓ Paiements Situations: {updated_expenses}/{total_expenses}")
        print(f"✓ Paiements Fournisseurs: {updated_suppliers}/{total_suppliers}")
        print(f"✓ Dépenses Globales: {updated_globale}/{total_globale}")
        print("\n✅ Mise à jour terminée avec succès!\n")

if __name__ == '__main__':
    try:
        update_caisse_projects()
    except Exception as e:
        print(f"\n❌ Erreur lors de la mise à jour: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
