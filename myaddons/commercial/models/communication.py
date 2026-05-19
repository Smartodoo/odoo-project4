from odoo import models, fields


MOTIF_SELECTION = [
    ('aucun', '<Aucun>'),
    # --- Divers ---
    ('divers_autre', 'Divers | Autre (à préciser)'),
    ('divers_demande_info_externe', 'Divers | Demande information externe (banque ou notaire)'),
    ('divers_suivi_administratif', 'Divers | Suivi administratif dossier'),
    ('divers_appel_interne', 'Divers | Appel interne / coordination équipe'),
    ('divers_double_prospect', 'Divers | Double prospect (fusion ou vérification)'),
    ('divers_correction_coordonnees', 'Divers | Correction coordonnées'),
    ('divers_maj_infos_prospect', 'Divers | Mise à jour informations prospect'),
    # --- Réclamation ---
    ('reclamation_conflit_blocage', 'Réclamation | Conflit sur blocage ou priorité lot'),
    ('reclamation_incident_com', 'Réclamation | Incident de communication'),
    ('reclamation_escalade', 'Réclamation | Demande escalade vers responsable'),
    ('reclamation_mecontentement_accueil', 'Réclamation | Mécontentement sur accueil ou commercial'),
    ('reclamation_mecontentement_prix', 'Réclamation | Mécontentement sur prix ou changement'),
    ('reclamation_info_recue', 'Réclamation | Réclamation sur information reçue'),
    # --- Clôture ---
    ('cloture_blacklist', 'Clôture | Blacklist interne'),
    ('cloture_sans_suite', 'Clôture | Clôture sans suite'),
    ('cloture_ne_plus_contacter', 'Clôture | Demande de ne plus être contacté'),
    ('cloture_contact_incorrect', 'Clôture | Contact incorrect'),
    ('cloture_numero_errone', 'Clôture | Numéro erroné'),
    ('cloture_injoignable', 'Clôture | Prospect injoignable'),
    ('cloture_reporte', 'Clôture | Prospect reporte à plus tard'),
    ('cloture_veut_louer', 'Clôture | Prospect veut louer'),
    ('cloture_trouve_ailleurs', 'Clôture | Prospect a trouvé ailleurs'),
    ('cloture_hors_budget', 'Clôture | Prospect hors budget'),
    ('cloture_non_interesse', 'Clôture | Prospect non intéressé'),
    # --- Objections ---
    ('objection_voir_autre_lot', 'Objections | Demande voir autre lot'),
    ('objection_dernier_prix', 'Objections | Demande dernier prix'),
    ('objection_crainte_demarches', 'Objections | Crainte démarches administratives'),
    ('objection_attente_promo', 'Objections | Attente promotion'),
    ('objection_comparaison_projets', 'Objections | Comparaison de projets'),
    ('objection_besoin_reflexion', 'Objections | Besoin réflexion'),
    ('objection_validation_conjoint', 'Objections | Objection validation conjoint / famille'),
    ('objection_parking_indispo', 'Objections | Objection parking indisponible'),
    ('objection_charges_elevees', 'Objections | Objection charges trop élevées'),
    ('objection_financement_incertain', 'Objections | Objection financement incertain'),
    ('objection_delai_livraison', 'Objections | Objection délai de livraison'),
    ('objection_prestations', 'Objections | Objection prestations / finitions'),
    ('objection_surface_plan', 'Objections | Objection surface / plan'),
    ('objection_etage_visavis', 'Objections | Objection étage / vis-à-vis'),
    ('objection_localisation', 'Objections | Objection localisation'),
    ('objection_prix_eleve', 'Objections | Objection prix trop élevé'),
    # --- Documents ---
    ('doc_verif_signature', 'Documents | Vérification signature / conformité'),
    ('doc_signature_organiser', 'Documents | Signature à organiser'),
    ('doc_envoi_contrat', 'Documents | Envoi contrat / pré-contrat'),
    ('doc_envoi_recu', 'Documents | Envoi reçu / confirmation paiement'),
    ('doc_incomplet', 'Documents | Document incomplet / correction demandée'),
    ('doc_reception_docs', 'Documents | Réception documents client'),
    ('doc_demande_attestation', 'Documents | Demande documents client (attestation travail)'),
    ('doc_demande_revenus', 'Documents | Demande documents client (revenus)'),
    ('doc_demande_piece_id', 'Documents | Demande documents client (pièce identité)'),
    ('doc_envoi_conditions', 'Documents | Envoi conditions / procédure de réservation'),
    ('doc_envoi_fiche_lot', 'Documents | Envoi fiche lot / fiche technique'),
    ('doc_envoi_rendu_3d', 'Documents | Envoi rendu 3D'),
    ('doc_envoi_plan_2d', 'Documents | Envoi plan 2D'),
    ('doc_envoi_grille_prix', 'Documents | Envoi grille des prix'),
    ('doc_envoi_brochure', 'Documents | Envoi brochure / plaquette'),
    # --- Pré-réservation ---
    ('preresa_ajout_options', 'Pré-réservation | Ajout options / prestations'),
    ('preresa_ajout_parking', 'Pré-réservation | Ajout parking / box / cellier'),
    ('preresa_changement_lot', 'Pré-réservation | Changement de lot'),
    ('preresa_annulation', 'Pré-réservation | Annulation pré-réservation'),
    ('preresa_paiement_avance', "Pré-réservation | Paiement d'avance / confirmation paiement"),
    ('preresa_passage', 'Pré-réservation | Passage à la pré-réservation (création dossier)'),
    ('preresa_confirmation_prix', 'Pré-réservation | Confirmation du prix final'),
    ('preresa_negociation', 'Pré-réservation | Négociation sur lot / conditions'),
    ('preresa_concurrence', 'Pré-réservation | Concurrence sur lot'),
    ('preresa_prolongation', 'Pré-réservation | Prolongation du blocage'),
    ('preresa_blocage_temp', 'Pré-réservation | Blocage temporaire du lot'),
    ('preresa_validation_finale', 'Pré-réservation | Validation finale du lot'),
    ('preresa_selection_lot', 'Pré-réservation | Sélection du lot (shortlist)'),
    ('preresa_intention', 'Pré-réservation | Intention de pré-réservation'),
    # --- Visite / RDV ---
    ('visite_demande_itineraire', 'Visite_RDV | Demande itinéraire / Google Maps'),
    ('visite_avec_architecte', 'Visite_RDV | Visite avec architecte ou expert'),
    ('visite_en_famille', 'Visite_RDV | Visite en famille'),
    ('visite_compte_rendu', 'Visite_RDV | Compte rendu de visite'),
    ('visite_rdv_manque', 'Visite_RDV | Rendez-vous manqué (no-show)'),
    ('visite_annulation_rdv', 'Visite_RDV | Annulation de rendez-vous'),
    ('visite_report_rdv', 'Visite_RDV | Report de rendez-vous'),
    ('visite_rappel_avant_rdv', 'Visite_RDV | Rappel avant rendez-vous (J-1 / H-2)'),
    ('visite_confirmation_rdv', 'Visite_RDV | Confirmation de rendez-vous'),
    ('visite_rdv_bureau', 'Visite_RDV | RDV bureau commercial'),
    ('visite_orga_appart_temoin', 'Visite_RDV | Organisation de visite (appartement témoin)'),
    ('visite_orga_chantier', 'Visite_RDV | Organisation de visite (chantier)'),
    ('visite_proposition', 'Visite_RDV | Proposition de visite'),
    # --- Financement ---
    ('finance_changement_mode', 'Financement | Changement mode de paiement'),
    ('finance_coordination_banque', 'Financement | Coordination banque / attestation'),
    ('finance_justificatifs_revenus', 'Financement | Justificatifs de revenus demandés'),
    ('finance_frais_annexes', "Financement | Frais d'annexes (notaire, enregistrement)"),
    ('finance_remise', 'Financement | Remise / geste commercial'),
    ('finance_avance_acompte', 'Financement | Avance / acompte'),
    ('finance_echeancier', 'Financement | Échéancier / tranches'),
    ('finance_modalites', 'Financement | Modalités de paiement'),
    ('finance_autofinancement', 'Financement | Autofinancement + crédit (mixte)'),
    ('finance_aide_etat', "Financement | Aide de l'État (CNL / autres)"),
    ('finance_credit_refus', 'Financement | Crédit bancaire refus ou blocage'),
    ('finance_cash', 'Financement | Paiement cash (comptant)'),
    ('finance_verif_budget', 'Financement | Vérification budget'),
    # --- Informations ---
    ('info_negociation_initiale', 'Informations | Négociation initiale (dernier prix)'),
    ('info_demande_promoteur', "Informations | Demande d'informations sur le promoteur"),
    ('info_penalites_clauses', 'Informations | Demande de pénalités / clauses'),
    ('info_conditions_reservation', 'Informations | Demande de conditions de réservation'),
    ('info_comparaison_residence', 'Informations | Comparaison avec autre résidence / autre projet'),
    ('info_localisation', 'Informations | Demande de localisation / accès / environnement'),
    ('info_situation_juridique', 'Informations | Demande de situation juridique (EDD / acte)'),
    ('info_charges_syndic', 'Informations | Demande de charges / syndic / copropriété'),
    ('info_parking', 'Informations | Demande de parking / box / cellier'),
    ('info_delais_livraison', 'Informations | Demande de délais de livraison'),
    ('info_prestations', 'Informations | Demande de prestations / finitions'),
    ('info_fiche_lot', 'Informations | Demande de fiche lot / fiche technique'),
    ('info_maquette_3d', 'Informations | Demande de maquette / rendu (3D)'),
    ('info_plan_2d', 'Informations | Demande de plan (2D)'),
    ('info_etage_orientation', "Informations | Demande d'étage / orientation / vue"),
    ('info_surface_typologies', 'Informations | Demande de surface / typologies (F2/F3/F4)'),
    ('info_disponibilites', 'Informations | Demande de disponibilités'),
    ('info_prix', 'Informations | Demande de prix'),
    # --- Relance ---
    ('relance_besoin_reflexion', 'Relance | Relance suite à besoin réflexion'),
    ('relance_promesse_rappel', 'Relance | Relance suite à promesse de rappel'),
    ('relance_changement_prix', 'Relance | Relance après changement de prix / dispo'),
    ('relance_fin_mois', "Relance | Relance fin de mois / fin d'offre"),
    ('relance_prospect_silencieux', 'Relance | Relance prospect silencieux'),
    ('relance_rdv_manque', 'Relance | Relance après rendez-vous manqué (no-show)'),
    ('relance_apres_visite', 'Relance | Relance après visite'),
    ('relance_apres_devis', 'Relance | Relance après devis / offre'),
    ('relance_apres_envoi_docs', 'Relance | Relance après envoi de documents'),
    ('relance_apres_sms', 'Relance | Relance après SMS'),
    ('relance_apres_whatsapp', 'Relance | Relance après message WhatsApp'),
    ('relance_apres_appel', 'Relance | Relance après appel sans réponse'),
    # --- Premier contact ---
    ('premier_confirmation_info', 'Premier contact | Confirmation de demande d\'information'),
    ('premier_presentation_projet', "Premier contact | Présentation du projet / de l'agence"),
    ('premier_verif_coordonnees', 'Premier contact | Vérification coordonnées / identité'),
    ('premier_qualification', 'Premier contact | Qualification initiale du prospect'),
    ('premier_appel_spontane', 'Premier contact | Appel entrant spontané'),
    ('premier_suite_campagne', 'Premier contact | Premier contact suite campagne (SMS / Ads)'),
    ('premier_suite_recommandation', 'Premier contact | Premier contact suite recommandation'),
    ('premier_suite_reseaux', 'Premier contact | Premier contact suite réseaux sociaux'),
    ('premier_suite_lead', 'Premier contact | Premier contact suite à lead (site)'),
]

RESULTAT_SELECTION = [
    ('aucun', '<Aucun>'),
    # --- Divers ---
    ('res_divers_autre', 'Divers | Autre résultat (à préciser)'),
    # --- Incident ---
    ('res_incident_conflit', 'Incident | Conflit avec prospect'),
    ('res_incident_communication', 'Incident | Incident de communication'),
    ('res_incident_escalade', 'Incident | Escalade vers responsable'),
    ('res_incident_reclamation', 'Incident | Réclamation ouverte'),
    # --- Clôture ---
    ('res_cloture_blacklist', 'Clôture | Blacklist interne'),
    ('res_cloture_ne_plus_contacter', 'Clôture | Demande de ne plus être contacté'),
    ('res_cloture_location', 'Clôture | Clôturé – location préférée'),
    ('res_cloture_achat_ailleurs', 'Clôture | Clôturé – achat ailleurs'),
    ('res_cloture_sans_suite', 'Clôture | Clôturé sans suite'),
    # --- Financement ---
    ('res_finance_modalites_validees', 'Financement | Modalités de paiement validées'),
    ('res_finance_cash_confirme', 'Financement | Paiement cash confirmé'),
    ('res_finance_aide_etat', "Financement | Aide de l'État en cours"),
    ('res_finance_credit_refuse', 'Financement | Crédit refusé'),
    ('res_finance_credit_en_cours', 'Financement | Crédit en cours'),
    ('res_finance_hors_budget', 'Financement | Hors budget'),
    ('res_finance_budget_valide', 'Financement | Budget validé'),
    # --- Pré-réservation ---
    ('res_preresa_annulation', 'Pré-réservation | Annulation de pré-réservation'),
    ('res_preresa_changement_lot', 'Pré-réservation | Changement de lot'),
    ('res_preresa_confirmee', 'Pré-réservation | Pré-réservation confirmée'),
    ('res_preresa_lot_bloque', 'Pré-réservation | Lot bloqué'),
    ('res_preresa_lot_preselectionne', 'Pré-réservation | Lot présélectionné'),
    # --- Documents ---
    ('res_doc_signature_effectuee', 'Documents | Signature effectuée'),
    ('res_doc_signature_organiser', 'Documents | Signature à organiser'),
    ('res_doc_devis_envoyee', 'Documents | Devis ou offre envoyée'),
    ('res_doc_dossier_incomplet', 'Documents | Dossier incomplet'),
    ('res_doc_documents_recus', 'Documents | Documents reçus'),
    ('res_doc_documents_envoyes', 'Documents | Documents envoyés'),
    # --- Action ---
    ('res_action_rdv_manque', 'Action | Rendez-vous manqué (no-show)'),
    ('res_action_visite_annulee', 'Action | Visite annulée'),
    ('res_action_rdv_annule', 'Action | Rendez-vous annulé'),
    ('res_action_rdv_reporte', 'Action | Rendez-vous reporté'),
    ('res_action_visite_effectuee', 'Action | Visite effectuée'),
    ('res_action_visite_fixee', 'Action | Visite fixée'),
    ('res_action_rdv_fixe', 'Action | Rendez-vous fixé'),
    ('res_action_rappel_planifie', 'Action | Rappel planifié'),
    # --- Intérêt ---
    ('res_interet_validation_famille', 'Intérêt | Validation famille ou conjoint requise'),
    ('res_interet_besoin_reflexion', 'Intérêt | Besoin de réflexion'),
    ('res_interet_comparaison', "Intérêt | Comparaison avec d'autres projets"),
    ('res_interet_pas_interesse', 'Intérêt | Pas intéressé'),
    ('res_interet_peu_interesse', 'Intérêt | Peu intéressé'),
    ('res_interet_tiede', 'Intérêt | Intéressé (prospect tiède)'),
    ('res_interet_chaud', 'Intérêt | Très intéressé (prospect chaud)'),
    # --- Non contact ---
    ('res_non_contact_reseau', 'Non contact | Problème réseau ou qualité ligne'),
    ('res_non_contact_appel_coupe', 'Non contact | Appel coupé'),
    ('res_non_contact_numero_incorrect', 'Non contact | Numéro incorrect ou injoignable'),
    ('res_non_contact_boite_vocale', 'Non contact | Boîte Vocale'),
    ('res_non_contact_eteint', 'Non contact | Téléphone éteint ou indisponible'),
    ('res_non_contact_ligne_occupee', 'Non contact | Ligne occupée'),
    ('res_non_contact_aucune_reponse', 'Non contact | Aucune réponse'),
    # --- Contact ---
    ('res_contact_reporte', 'Contact | Contact reporté (rappel demandé)'),
    ('res_contact_whatsapp', 'Contact | Contact uniquement par WhatsApp'),
    ('res_contact_via_tiers', 'Contact | Contact via tiers (famille ou collègue)'),
    ('res_contact_partiel', 'Contact | Contact partiel (échange limité)'),
    ('res_contact_etabli', 'Contact | Contact établi avec le prospect'),
]


class CommercialCommunication(models.Model):
    _name = 'commercial.communication'
    _description = 'Communication commerciale'
    _order = 'date_heure desc'

    partner_id = fields.Many2one(
        'res.partner', string="Contact", ondelete='cascade')
    date_heure = fields.Datetime(
        string="Date et heure", required=True, default=fields.Datetime.now)
    type_communication = fields.Selection([
        ('entrant', 'Entrant'),
        ('sortant', 'Sortant'),
    ], string="Type", default='entrant', required=True)
    motif = fields.Selection(
        MOTIF_SELECTION, string="Motif", default='aucun')
    resultat = fields.Selection(
        RESULTAT_SELECTION, string="Résultat", default='aucun')
    note = fields.Text(string="Note")
    commercial_id = fields.Many2one(
        'res.users', string="Commercial",
        default=lambda self: self.env.user, readonly=True)

    def action_save_and_close(self):
        return {'type': 'ir.actions.act_window_close'}