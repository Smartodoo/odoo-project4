from odoo import fields, models, api


class Sinistre(models.Model):
    _name = 'sinistre'
    _description = 'sinistre'
    _order = 'date_accident desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    user_id = fields.Many2one('res.users', string="Utilisateur actuel", default=lambda self: self.env.user)
    vehicle_id = fields.Many2one('fleet.vehicle', 'Véhicule', tracking=True, required=True)
    license_plate = fields.Char(tracking=True, string="Plaque d'immatriculation",
                                help="Numéro de plaque d'immatriculation du véhicule")
    date_accident = fields.Date("Date de l'accident", help="Date de l'accident")
    agence_assurance1 = fields.Many2one('res.partner', "Agence d'assurance", tracking=True, help="Agence d'assurance",
                                        domain=[('contact_type', '=', 'SUPPLIER'), ])
    numero_police = fields.Char('Numéro de police', tracking=True, help='Numéro de police')

    driver_id = fields.Many2one('res.partner', 'Conducteur', tracking=True, help='Adresse du conducteur du véhicule',
                                copy=False)

    accident_type = fields.Selection([('tiers', 'Avec adversaire'), ('sans', 'Sans adversaire')],
                                     string="Type d'accident",
                                     default='sans', tracking=True, help="type d'accident")
    nom_tiers = fields.Char('Nom complet du tiers', tracking=True, help='Nom du tiers')
    prenom_tiers = fields.Char('Adresse du tiers', tracking=True, help='Prenom du tiers')
    agence_assurance2 = fields.Char('Agence dassurance', tracking=True, help="Agence d'assurance")
    degat_sur_vehicule = fields.Char('Degat sur vehicule', tracking=True, help='Degat sur vehicule')
    date_expertise = fields.Date('Date dexpertisé', help="Date d'expertisé")
    nom_expert = fields.Char("Nom de l'expert", tracking=True, help="Nom de l'expert")
    numero_cloque = fields.Integer('Numéro de chéque', tracking=True, help='Numéro de chéque')
    date_reparation = fields.Date('Date de payment', help="Date de payment")
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.company.currency_id)
    montant_reparation = fields.Monetary('Montant', currency_field='currency_id', tracking=True,
                                         help='Montant')
    degat_sur_vehicule1 = fields.Char('Degat sur vehicule', tracking=True, help='Degat sur vehicule')
    degat_sur_vehicule2 = fields.Html('Degat sur vehicule', help='Degat sur vehicule')
    degat_sur_vehicule_html = fields.Html('Degat sur vehicule', help='Degat sur vehicule')
    numero_pv = fields.Char('Numéro de PV', tracking=True, help='Numéro de PV')
    payment_state = fields.Selection([
        ('payé', 'Régler'),
        ('pas_payé', 'Non régler')
    ], string='État du réglement', default='pas_payé')

    accident_type = fields.Selection([('tiers', 'Avec adversaire'), ('sans', 'Sans adversaire')],
                                     string="Type d'accident",
                                     default='sans', tracking=True, help="type d'accident")
    technical_file = fields.Many2many('ir.attachment', string="Téléchargez vos constats", tracking=True)
    technical_file_name = fields.Char(string='Nom du Fichier', tracking=True)
    state = fields.Selection([('draft', 'En Attente de PV'), ('en_cours', 'En cours'), ('termine', 'Clôturé')],
                             string='État', tracking=True, help="État du sinistre", readonly=False, default='draft')

    date_effet = fields.Date('Date d\'effet', tracking=True, help="Date d'effet du sinistre")
    date_expertation = fields.Date('Date d\'expertation', tracking=True, help="Date d'expertation du sinistre")
    assurence = fields.Char("Compagnie d'assurance", tracking=True, help="Assurance du sinistre")
    assurence2 = fields.Char("Compagnie d'assurance", tracking=True, help="Assurance du sinistre")
    date_effet_1 = fields.Date('Date d\'effet', tracking=True, help="Date d'effet du sinistre")
    date_expertation_1 = fields.Date('Date d\'expertation', tracking=True, help="Date d'expertation du sinistre")
    # numero_police = fields.Char('Numéro de police', tracking=True, help='Numéro de police')
    numero_police2 = fields.Char('Numéro de police', tracking=True, help='Numéro de police')
    numero_sinistre = fields.Char('Numéro de sinistre', tracking=True, help='Numéro de sinistre')
    numero_serie = fields.Char('Numéro de série', tracking=True, help='Numéro de série du véhicule')
    circonstances = fields.Text("Circonstances de l'accident", tracking=True,
                                help="Description des circonstances de l'accident")
    fautif = fields.Selection([
        ('notre_vehicule', 'Notre véhicule'),
        ('tiers', 'Le tiers'),
        ('partage', 'Responsabilité partagée'),
        ('non_determine', 'Non déterminé'),
    ], string='Fautif', tracking=True, help="Partie responsable de l'accident")
    cout_reparation = fields.Char('Cout de réparation', tracking=True)
    Duree_immobilisation = fields.Char("Durée d'immobilisation", tracking=True)
    time_type = fields.Selection([
        ('day', 'jour(s)'),
        ('month', 'mois'),
    ], string='', default='day', required=True)
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        if self.vehicle_id:
            self.license_plate = self.vehicle_id.license_plate
            self.driver_id = self.vehicle_id.driver_id

            # Search for the most recent insurance contract (including expired/closed ones)
            contract = self.env['fleet.vehicle.log.contract'].with_context(active_test=False).search([
                ('vehicle_id', '=', self.vehicle_id.id),
                ('cost_subtype_id.name', 'ilike', 'assurance'),
            ], order='expiration_date desc', limit=1)
            if contract:
                self.agence_assurance1 = contract.insurer_id.id
                self.numero_police = contract.numero_police
                self.assurence2 = contract.societe_assurance
                self.date_effet = contract.start_date
                self.date_expertation = contract.expiration_date
            else:
                self.agence_assurance1 = False
                self.numero_police = False
                self.assurence2 = False
                self.date_effet = False
                self.date_expertation = False

    @api.onchange('montant_reparation')
    def _onchange_montant_reparation(self):
        if self.montant_reparation != 0:
            self.payment_state = 'payé'
        elif self.montant_reparation == 0:
            self.payment_state = 'pas_payé'


class FleetVhicleModelInherit(models.Model):
    _inherit = 'fleet.vehicle.model'

    vehicle_type_1 = fields.Many2one('vehicle.type', string='Type de véhicule', required=True)

    def update_old_record_with_vehicle_type(self):
        for rec in self:
            if rec.vehicle_type:
                if rec.vehicle_type == 'car':
                    vehicle_type = self.env['vehicle.type'].search([('name', '=', 'Voiture')]).id
                    if vehicle_type:
                        rec.vehicle_type_1 = vehicle_type
                else:
                    vehicle_type = self.env['vehicle.type'].search([('name', '=', 'Vélo')]).id
                    if vehicle_type:
                        rec.vehicle_type_1 = vehicle_type


class VehicleType(models.Model):
    _name = 'vehicle.type'
    _description = 'Type de véhicule'

    name = fields.Char(string='Type de véhicule', help='Type de véhicule')
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user)


class VehicleAvailability(models.Model):
    _name = 'vehicle.availability'
    _description = 'Disponibilité du véhicule'

    name = fields.Char(string='Disponibilité', required=True, help='Statut de disponibilité du véhicule')
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)


class FleetVehicleInherit(models.Model):
    _inherit = 'fleet.vehicle'

    availability_id = fields.Many2one('vehicle.availability', string='Disponibilité du véhicule', help='Statut de disponibilité du véhicule')

    # Document type fields
    document_type = fields.Selection([
        ('carte_grise', 'Carte Grise'),
        ('carte_jaune', 'Carte Jaune'),
    ], string='Type de document')
    nom_proprietaire = fields.Char(string='Nom de propriétaire')
    date_emission = fields.Date(string="Date d'émission")
    date_expiration = fields.Date(string="Date d'expiration")


class AssuranceType(models.Model):
    _name = 'assurance.type'
    _description = "Type d'assurance"

    name = fields.Char(string="Type d'assurance", required=True)
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)


class FleetVehicleLogContractInherit(models.Model):
    _inherit = 'fleet.vehicle.log.contract'

    # Fields for Assurance
    type_assurance_id = fields.Many2one('assurance.type', string="Type d'assurance")
    societe_assurance = fields.Char(string="Société d'assurance")
    numero_police = fields.Char(string="N° Police")
    cout_assurance = fields.Float(string="Coût")
    description_assurance = fields.Text(string="Description")

    # Fields for Vignette
    date_emission_vignette = fields.Date(string="Date d'émission")
    date_expiration_vignette = fields.Date(string="Date d'expiration")
    cout_vignette = fields.Float(string="Coût")

    # Charge (Amande et Pénalité)
    charge_ids = fields.One2many('amande.penalite', 'contract_id', string="Charges")
    charge_count = fields.Integer(string="Nombre de charges", compute='_compute_charge_count')

    # Computed fields for visibility
    is_assurance = fields.Boolean(string="Est une assurance", compute='_compute_contract_type')
    is_vignette = fields.Boolean(string="Est une vignette", compute='_compute_contract_type')

    @api.depends('charge_ids')
    def _compute_charge_count(self):
        for record in self:
            record.charge_count = len(record.charge_ids)

    def action_view_charges(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Charges',
            'res_model': 'amande.penalite',
            'view_mode': 'tree,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
        }

    @api.depends('cost_subtype_id')
    def _compute_contract_type(self):
        for record in self:
            if record.cost_subtype_id and record.cost_subtype_id.name:
                type_name = record.cost_subtype_id.name.lower()
                record.is_assurance = type_name == 'assurance'
                record.is_vignette = type_name == 'vignette'
            else:
                record.is_assurance = False
                record.is_vignette = False


class AmandePenalite(models.Model):
    _name = 'amande.penalite'
    _description = "Amande et Pénalité"
    _order = 'date_emission desc'

    name = fields.Char(string="Référence", readonly=True, default='Nouveau', copy=False)
    type = fields.Many2one('type.amande.penalite', string="Type")
    reference = fields.Char(string="Référence")
    date_emission = fields.Date(string="Date d'émission")
    date_expiration = fields.Date(string="Date d'expiration")
    cout = fields.Float(string="Coût")
    autorite = fields.Many2one('autorite.penalite', string="Autorité")
    description = fields.Text(string="Description")
    contract_id = fields.Many2one('fleet.vehicle.log.contract', string="Contrat")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nouveau') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].next_by_code('amande.penalite') or 'Nouveau'
        return super().create(vals_list)


class MaintenanceType(models.Model):
    _name = 'maintenance.type'
    _description = "Type de maintenance"

    name = fields.Char(string="Type de maintenance", required=True)
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)


class VidangeType(models.Model):
    _name = 'vidange.type'
    _description = "Type de vidange"

    name = fields.Char(string="Type de vidange", required=True)
    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)


class FleetVehicleLogServicesInherit(models.Model):
    _inherit = 'fleet.vehicle.log.services'

    # Fields for Maintenance
    type_maintenance_id = fields.Many2one('maintenance.type', string="Type de maintenance")
    prochain_operation = fields.Date(string="Prochaine opération")
    description_maintenance = fields.Text(string="Description")

    # Fields for Entretien
    nature_entretien = fields.Char(string="Nature de l'entretien")
    dernier_releve_km = fields.Float(string="Dernier relevé kilométrique")

    # Fields for Carburant
    n_litre = fields.Float(string="N Litre")
    nouveau_releve = fields.Float(string="Nouveau relevé")
    mode_paiement = fields.Selection([
        ('espece', 'Espèce'),
        ('cheque', 'Chèque'),
        ('virement', 'Virement'),
        ('carte', 'Carte bancaire'),
    ], string="Mode de paiement")
    reglement = fields.Float(string="Règlement")

    # Fields for Vidange
    nombre_litre_charge = fields.Float(string="Nombre de litres chargés")
    prochain_vidange = fields.Date(string="Prochain vidange")
    type_vidange_id = fields.Many2one('vidange.type', string="Type de vidange")

    # Computed fields for visibility
    is_maintenance = fields.Boolean(string="Est une maintenance", compute='_compute_service_type')
    is_entretien = fields.Boolean(string="Est un entretien", compute='_compute_service_type')
    is_carburant = fields.Boolean(string="Est un carburant", compute='_compute_service_type')
    is_vidange = fields.Boolean(string="Est une vidange", compute='_compute_service_type')

    @api.depends('service_type_id')
    def _compute_service_type(self):
        for record in self:
            if record.service_type_id and record.service_type_id.name:
                service_name = record.service_type_id.name.lower()
                record.is_maintenance = service_name == 'maintenance'
                record.is_entretien = service_name == 'entretien'
                record.is_carburant = service_name == 'carburant'
                record.is_vidange = service_name == 'vidange'
            else:
                record.is_maintenance = False
                record.is_entretien = False
                record.is_carburant = False
                record.is_vidange = False


class TypeAmandePenalite(models.Model):
    _name = 'type.amande.penalite'
    _description = "Type d'amande et pénalité"

    name = fields.Char(string="Nom", required=True)


class AutoritePenalite(models.Model):
    _name = 'autorite.penalite'
    _description = "Autorité de pénalité"

    name = fields.Char(string="Nom", required=True)
