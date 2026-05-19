from odoo import models, fields, api


class CommercialStatistique(models.Model):
    _name = 'commercial.statistique'
    _description = 'Statistique Commercial'

    name = fields.Char(string="Nom", compute='_compute_name', store=True)
    projet_id = fields.Many2one('commercial.projet', string="Projet", required=True, ondelete='cascade')

    # Filtres
    inclure_habitat = fields.Boolean(string="Habitat", default=True)
    inclure_parking = fields.Boolean(string="Parking", default=True)
    inclure_local = fields.Boolean(string="Local", default=True)
    inclure_service = fields.Boolean(string="Service", default=True)
    date_du = fields.Date(string="Du")
    date_au = fields.Date(string="Au")

    # Champs pour la vue tree
    total_lots = fields.Integer(string="Total Lots", compute='_compute_summary', store=False)
    lots_vendus = fields.Integer(string="Vendus", compute='_compute_summary', store=False)
    lots_reserves = fields.Integer(string="Réservés", compute='_compute_summary', store=False)
    pourcentage_vente = fields.Float(string="% Vente", compute='_compute_summary', store=False)
    ca_previsionnel = fields.Float(string="CA Prévisionnel", compute='_compute_summary', store=False)
    ca_actuel = fields.Float(string="CA Actuel", compute='_compute_summary', store=False)

    # Dashboard HTML
    dashboard_html = fields.Html(string="Tableau de Bord", compute='_compute_dashboard', sanitize=False)

    @api.depends('projet_id')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.projet_id.name or 'Nouveau'

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_lot_type(self, lot):
        type_name = (lot.categorie_id.type_lot_id.name or '').upper()
        if 'PARKING' in type_name:
            return 'parking'
        elif 'LOCAL' in type_name:
            return 'local'
        elif 'SERVICE' in type_name:
            return 'service'
        return 'habitat'

    def _get_lot_reference_date(self, lot):
        """Retourne la date de référence du lot pour le filtrage:
        - Vendu: première date d'encaissement des échéances payées
        - Réservé: première date d'encaissement des versements confirmés
        """
        if lot.state == 'vendu':
            dates = []
            for p in lot.paiement_ids:
                for e in p.echeance_ids.filtered(lambda e: e.etat == 'paye' and e.date_encaissement):
                    dates.append(e.date_encaissement)
                if hasattr(p, 'echeance_apport_ids'):
                    for e in p.echeance_apport_ids.filtered(lambda e: e.etat == 'paye' and e.date_encaissement):
                        dates.append(e.date_encaissement)
            return min(dates) if dates else False
        elif lot.state == 'reserve':
            dates = [
                v.date_encaissement for v in lot.versement_ids
                if v.state == 'confirme' and v.date_encaissement
            ]
            return min(dates) if dates else False
        return False

    def _get_filtered_lots(self):
        self.ensure_one()
        if not self.projet_id:
            return self.env['commercial.lot']
        lots = self.env['commercial.lot'].search([('projet_id', '=', self.projet_id.id)])
        included = set()
        if self.inclure_habitat:
            included.add('habitat')
        if self.inclure_parking:
            included.add('parking')
        if self.inclure_local:
            included.add('local')
        if self.inclure_service:
            included.add('service')
        lots = lots.filtered(lambda l: self._get_lot_type(l) in included)
        # Filtrer par date de référence selon l'état du lot
        if self.date_du or self.date_au:
            def _in_date_range(lot):
                ref_date = self._get_lot_reference_date(lot)
                if not ref_date:
                    return False
                if self.date_du and ref_date < self.date_du:
                    return False
                if self.date_au and ref_date > self.date_au:
                    return False
                return True
            lots = lots.filtered(_in_date_range)
        return lots

    def _get_lot_total_paid(self, lot):
        date_du = self.date_du
        date_au = self.date_au
        # Versements confirmés filtrés par date d'encaissement
        total = 0
        for v in lot.versement_ids:
            if v.state != 'confirme':
                continue
            if date_du and v.date_encaissement and v.date_encaissement < date_du:
                continue
            if date_au and v.date_encaissement and v.date_encaissement > date_au:
                continue
            total += v.montant
        # Échéances payées filtrées par date_encaissement
        for p in lot.paiement_ids:
            for e in p.echeance_ids:
                if e.etat != 'paye':
                    continue
                if date_du and e.date_encaissement and e.date_encaissement < date_du:
                    continue
                if date_au and e.date_encaissement and e.date_encaissement > date_au:
                    continue
                total += e.montant
            if hasattr(p, 'echeance_apport_ids'):
                for e in p.echeance_apport_ids:
                    if e.etat != 'paye':
                        continue
                    if date_du and e.date_encaissement and e.date_encaissement < date_du:
                        continue
                    if date_au and e.date_encaissement and e.date_encaissement > date_au:
                        continue
                    total += e.montant
        return total

    def _format_amount(self, amount):
        if amount == 0:
            return "0,00 DA"
        negative = amount < 0
        amount = abs(amount)
        integer_part = int(amount)
        decimal_part = round((amount - integer_part) * 100)
        int_str = f"{integer_part:,}".replace(",", " ")
        result = f"{int_str},{decimal_part:02d} DA"
        return f"-{result}" if negative else result

    # -------------------------------------------------------------------------
    # Computed: summary (for tree view)
    # -------------------------------------------------------------------------

    @api.depends('projet_id', 'inclure_habitat', 'inclure_parking', 'inclure_local', 'inclure_service', 'date_du', 'date_au')
    def _compute_summary(self):
        for rec in self:
            if not rec.projet_id:
                rec.total_lots = rec.lots_vendus = rec.lots_reserves = 0
                rec.pourcentage_vente = rec.ca_previsionnel = rec.ca_actuel = 0
                continue
            lots = rec._get_filtered_lots()
            rec.total_lots = len(lots)
            rec.lots_vendus = len(lots.filtered(lambda l: l.state == 'vendu'))
            rec.lots_reserves = len(lots.filtered(lambda l: l.state == 'reserve'))
            rec.ca_previsionnel = sum(lots.mapped('montant_net_client'))
            rec.ca_actuel = sum(rec._get_lot_total_paid(l) for l in lots)
            rec.pourcentage_vente = (rec.ca_actuel / rec.ca_previsionnel * 100) if rec.ca_previsionnel > 0 else 0

    def action_print(self):
        self.ensure_one()
        return self.env.ref('commercial.action_report_statistique').report_action(self)

    def _get_report_data(self):
        """Prepare all data needed for the PDF report."""
        self.ensure_one()
        lots = self._get_filtered_lots()
        blocs = self.projet_id.bloc_ids

        total_lots = len(lots)
        n_dispo = len(lots.filtered(lambda l: l.state == 'disponible'))
        n_option = len(lots.filtered(lambda l: l.state == 'en_option'))
        n_reserve = len(lots.filtered(lambda l: l.state == 'reserve'))
        n_vendu = len(lots.filtered(lambda l: l.state == 'vendu'))
        ca_prev = sum(lots.mapped('montant_net_client'))
        ca_actuel = sum(self._get_lot_total_paid(l) for l in lots)
        pct_global = (ca_actuel / ca_prev * 100) if ca_prev > 0 else 0

        bloc_data = []
        for bloc in blocs:
            bloc_lots = lots.filtered(lambda l, b=bloc: l.bloc_id.id == b.id)
            if not bloc_lots:
                continue
            b_total = len(bloc_lots)
            b_dispo = len(bloc_lots.filtered(lambda l: l.state == 'disponible'))
            b_option = len(bloc_lots.filtered(lambda l: l.state == 'en_option'))
            b_reserve = len(bloc_lots.filtered(lambda l: l.state == 'reserve'))
            b_vendu = len(bloc_lots.filtered(lambda l: l.state == 'vendu'))
            b_ca_prev = sum(bloc_lots.mapped('montant_net_client'))
            b_ca_actuel = sum(self._get_lot_total_paid(l) for l in bloc_lots)
            b_pct = (b_ca_actuel / b_ca_prev * 100) if b_ca_prev > 0 else 0
            bloc_data.append({
                'code': bloc.code,
                'total': b_total, 'dispo': b_dispo, 'option': b_option,
                'reserve': b_reserve, 'vendu': b_vendu,
                'ca_prev': b_ca_prev, 'ca_actuel': b_ca_actuel, 'pct': b_pct,
            })

        state_map = {
            'disponible': 'Disponible',
            'en_option': 'Pré-réservation',
            'reserve': 'Réservé',
            'vendu': 'Vendu',
        }
        lot_data = []
        for lot in lots.sorted(lambda l: (l.bloc_id.code or '', l.numero_lot or '')):
            paid = self._get_lot_total_paid(lot)
            pct = min((paid / lot.montant_net_client * 100), 100) if lot.montant_net_client > 0 else 0
            reste = lot.montant_net_client - paid
            lot_data.append({
                'numero': lot.numero_lot or '',
                'bloc': lot.bloc_id.code or '',
                'etage': lot.etage_id.name or '',
                'type': lot.categorie_id.type_lot_id.name or '',
                'nature': lot.categorie_id.nature_id.name or '',
                'surface': lot.surface_globale,
                'prix_net': lot.montant_net_client,
                'paid': paid, 'reste': reste, 'pct': pct,
                'state': state_map.get(lot.state, lot.state or ''),
            })

        return {
            'total_lots': total_lots, 'n_dispo': n_dispo, 'n_option': n_option,
            'n_reserve': n_reserve, 'n_vendu': n_vendu,
            'ca_prev': ca_prev, 'ca_actuel': ca_actuel, 'pct_global': pct_global,
            'blocs': bloc_data, 'lots': lot_data,
        }

    # -------------------------------------------------------------------------
    # Computed: Dashboard HTML
    # -------------------------------------------------------------------------

    @api.depends('projet_id', 'inclure_habitat', 'inclure_parking', 'inclure_local', 'inclure_service', 'date_du', 'date_au')
    def _compute_dashboard(self):
        for rec in self:
            if not rec.projet_id:
                rec.dashboard_html = (
                    '<div style="text-align:center;padding:60px;color:#999;">'
                    '<h3>Sélectionnez un projet pour afficher les statistiques</h3></div>'
                )
                continue

            lots = rec._get_filtered_lots()
            blocs = rec.projet_id.bloc_ids

            # --- Statistiques globales ---
            total_lots = len(lots)
            n_dispo = len(lots.filtered(lambda l: l.state == 'disponible'))
            n_option = len(lots.filtered(lambda l: l.state == 'en_option'))
            n_reserve = len(lots.filtered(lambda l: l.state == 'reserve'))
            n_vendu = len(lots.filtered(lambda l: l.state == 'vendu'))

            ca_prev = sum(lots.mapped('montant_net_client'))
            ca_actuel = sum(rec._get_lot_total_paid(l) for l in lots)
            pct_global = (ca_actuel / ca_prev * 100) if ca_prev > 0 else 0

            # --- Tableau par Bloc ---
            bloc_rows = ""
            for bloc in blocs:
                bloc_lots = lots.filtered(lambda l, b=bloc: l.bloc_id.id == b.id)
                if not bloc_lots:
                    continue
                b_total = len(bloc_lots)
                b_dispo = len(bloc_lots.filtered(lambda l: l.state == 'disponible'))
                b_option = len(bloc_lots.filtered(lambda l: l.state == 'en_option'))
                b_reserve = len(bloc_lots.filtered(lambda l: l.state == 'reserve'))
                b_vendu = len(bloc_lots.filtered(lambda l: l.state == 'vendu'))
                b_ca_prev = sum(bloc_lots.mapped('montant_net_client'))
                b_ca_actuel = sum(rec._get_lot_total_paid(l) for l in bloc_lots)
                b_pct = (b_ca_actuel / b_ca_prev * 100) if b_ca_prev > 0 else 0

                bloc_rows += f"""
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:10px 12px;font-weight:600;">{bloc.code}</td>
                    <td style="padding:10px 12px;text-align:center;font-weight:700;">{b_total}</td>
                    <td style="padding:10px 12px;text-align:center;color:#28a745;font-weight:600;">{b_dispo}</td>
                    <td style="padding:10px 12px;text-align:center;color:#17a2b8;font-weight:600;">{b_option}</td>
                    <td style="padding:10px 12px;text-align:center;color:#e67e00;font-weight:600;">{b_reserve}</td>
                    <td style="padding:10px 12px;text-align:center;color:#6f42c1;font-weight:600;">{b_vendu}</td>
                    <td style="padding:10px 12px;text-align:center;">
                        <span style="background:{'#d4edda' if b_pct >= 75 else '#fff3cd' if b_pct >= 25 else '#f8d7da'};
                               color:{'#155724' if b_pct >= 75 else '#856404' if b_pct >= 25 else '#721c24'};
                               padding:3px 10px;border-radius:12px;font-weight:700;font-size:12px;">
                            {b_pct:.1f}%
                        </span>
                    </td>
                    <td style="padding:10px 12px;text-align:right;font-size:12px;">{rec._format_amount(b_ca_prev)}</td>
                    <td style="padding:10px 12px;text-align:right;font-size:12px;font-weight:600;">{rec._format_amount(b_ca_actuel)}</td>
                </tr>"""

            # --- Tableau détaillé par Lot ---
            lot_rows = ""
            for lot in lots.sorted(lambda l: (l.bloc_id.code or '', l.numero_lot or '')):
                total_paid = rec._get_lot_total_paid(lot)
                pct = min((total_paid / lot.montant_net_client * 100), 100) if lot.montant_net_client > 0 else 0
                reste = lot.montant_net_client - total_paid

                state_map = {
                    'disponible': ('Disponible', '#28a745', '#d4edda', '#155724'),
                    'en_option': ('Pré-réservation', '#17a2b8', '#d1ecf1', '#0c5460'),
                    'reserve': ('Réservé', '#e67e00', '#fff3cd', '#856404'),
                    'vendu': ('Vendu', '#6f42c1', '#e8daef', '#4a235a'),
                }
                state_label, _, bg, fg = state_map.get(lot.state, (lot.state, '#6c757d', '#e2e3e5', '#383d41'))

                if pct >= 75:
                    bar_color = '#28a745'
                elif pct >= 50:
                    bar_color = '#17a2b8'
                elif pct >= 25:
                    bar_color = '#e67e00'
                else:
                    bar_color = '#dc3545'

                client_name = lot.client_id.name or ''
                lot_rows += f"""
                <tr style="border-bottom:1px solid #f0f0f0;">
                    <td style="padding:8px 12px;">{client_name}</td>
                    <td style="padding:8px 12px;font-weight:600;">{lot.numero_lot or ''}</td>
                    <td style="padding:8px 12px;">{lot.bloc_id.code or ''}</td>
                    <td style="padding:8px 12px;">{lot.etage_id.name or ''}</td>
                    <td style="padding:8px 12px;font-size:12px;">{lot.categorie_id.type_lot_id.name or ''}</td>
                    <td style="padding:8px 12px;font-size:12px;">{lot.categorie_id.nature_id.name or ''}</td>
                    <td style="padding:8px 12px;text-align:right;">{lot.surface_globale:.2f}</td>
                    <td style="padding:8px 12px;text-align:right;font-size:12px;">{rec._format_amount(lot.montant_net_client)}</td>
                    <td style="padding:8px 12px;text-align:right;font-size:12px;color:#28a745;font-weight:600;">{rec._format_amount(total_paid)}</td>
                    <td style="padding:8px 12px;text-align:right;font-size:12px;color:#dc3545;">{rec._format_amount(reste)}</td>
                    <td style="padding:8px 12px;min-width:160px;">
                        <div style="display:flex;align-items:center;gap:6px;">
                            <div style="flex:1;background:#e9ecef;border-radius:6px;height:18px;min-width:80px;overflow:hidden;">
                                <div style="width:{pct:.0f}%;height:100%;background:{bar_color};border-radius:6px;"></div>
                            </div>
                            <span style="font-weight:700;font-size:12px;min-width:42px;text-align:right;">{pct:.1f}%</span>
                        </div>
                    </td>
                    <td style="padding:8px 12px;text-align:center;">
                        <span style="background:{bg};color:{fg};padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;white-space:nowrap;">
                            {state_label}
                        </span>
                    </td>
                </tr>"""

            # --- Graphe en barres par Bloc ---
            max_lots = max((len(lots.filtered(lambda l, b=b: l.bloc_id.id == b.id)) for b in blocs), default=1) or 1
            bar_chart_html = ""
            for bloc in blocs:
                bloc_lots = lots.filtered(lambda l, b=bloc: l.bloc_id.id == b.id)
                if not bloc_lots:
                    continue
                bt = len(bloc_lots)
                bv = len(bloc_lots.filtered(lambda l: l.state == 'vendu'))
                br = len(bloc_lots.filtered(lambda l: l.state == 'reserve'))
                bo = len(bloc_lots.filtered(lambda l: l.state == 'en_option'))
                bd = len(bloc_lots.filtered(lambda l: l.state == 'disponible'))

                bar_chart_html += f"""
                <div style="display:flex;align-items:center;margin-bottom:8px;">
                    <div style="width:80px;font-size:12px;font-weight:600;text-align:right;padding-right:10px;white-space:nowrap;">{bloc.code}</div>
                    <div style="flex:1;display:flex;height:30px;background:#f5f5f5;border-radius:6px;overflow:hidden;">
                        {'<div style="width:' + str(bv / max_lots * 100) + '%;background:#6f42c1;display:flex;align-items:center;justify-content:center;color:white;font-size:10px;font-weight:600;">' + (str(bv) if bv else '') + '</div>' if bv else ''}
                        {'<div style="width:' + str(br / max_lots * 100) + '%;background:#e67e00;display:flex;align-items:center;justify-content:center;color:white;font-size:10px;font-weight:600;">' + (str(br) if br else '') + '</div>' if br else ''}
                        {'<div style="width:' + str(bo / max_lots * 100) + '%;background:#17a2b8;display:flex;align-items:center;justify-content:center;color:white;font-size:10px;font-weight:600;">' + (str(bo) if bo else '') + '</div>' if bo else ''}
                        {'<div style="width:' + str(bd / max_lots * 100) + '%;background:#28a745;display:flex;align-items:center;justify-content:center;color:white;font-size:10px;font-weight:600;">' + (str(bd) if bd else '') + '</div>' if bd else ''}
                    </div>
                    <div style="width:35px;font-size:12px;text-align:center;font-weight:600;padding-left:6px;">{bt}</div>
                </div>"""

            # --- Camembert CSS ---
            if total_lots > 0:
                p1 = n_vendu / total_lots * 100
                p2 = p1 + n_reserve / total_lots * 100
                p3 = p2 + n_option / total_lots * 100
                pie_gradient = (
                    f"conic-gradient("
                    f"#6f42c1 0% {p1:.1f}%, "
                    f"#e67e00 {p1:.1f}% {p2:.1f}%, "
                    f"#17a2b8 {p2:.1f}% {p3:.1f}%, "
                    f"#28a745 {p3:.1f}% 100%)"
                )
            else:
                pie_gradient = "conic-gradient(#e0e0e0 0% 100%)"

            # --- Stats par type de lot ---
            type_labels = {'habitat': 'Habitat', 'parking': 'Parking', 'local': 'Local', 'service': 'Service'}
            type_stats_html = ""
            for tkey, tlabel in type_labels.items():
                type_lots = lots.filtered(lambda l, t=tkey: rec._get_lot_type(l) == t)
                t_total = len(type_lots)
                t_res = len(type_lots.filtered(lambda l: l.state in ('reserve', 'vendu')))
                t_pct = (t_res / t_total * 100) if t_total > 0 else 0
                type_stats_html += f"""
                <div style="margin-bottom:14px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                        <span style="font-size:13px;font-weight:600;">{tlabel}</span>
                        <span style="font-size:13px;font-weight:700;color:#1a237e;">{t_pct:.1f}%</span>
                    </div>
                    <div style="background:#e9ecef;border-radius:6px;height:8px;overflow:hidden;">
                        <div style="width:{t_pct:.0f}%;height:100%;background:#0d6efd;border-radius:6px;"></div>
                    </div>
                    <div style="font-size:11px;color:#888;margin-top:3px;">
                        {t_res} réservés/vendus sur {t_total} lots
                    </div>
                </div>"""

            # =====================================================================
            # HTML COMPLET
            # =====================================================================
            rec.dashboard_html = f"""
            <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:1400px;">

                <!-- === EN-TETE === -->
                <div style="background:linear-gradient(135deg,#1a237e,#3949ab);color:white;padding:24px;border-radius:14px;margin-bottom:24px;">
                    <h2 style="margin:0 0 16px 0;font-size:24px;letter-spacing:0.5px;">{rec.projet_id.name or ''}</h2>
                    <div style="display:flex;align-items:center;gap:24px;flex-wrap:wrap;">
                        <div style="flex:1;min-width:250px;">
                            <div style="font-size:12px;opacity:0.8;margin-bottom:6px;">Vente Globale</div>
                            <div style="background:rgba(255,255,255,0.15);border-radius:10px;height:28px;overflow:hidden;">
                                <div style="width:{min(pct_global, 100):.0f}%;height:100%;background:rgba(255,255,255,0.85);border-radius:10px;
                                     display:flex;align-items:center;justify-content:center;font-weight:800;color:#1a237e;font-size:13px;
                                     min-width:50px;">
                                    {pct_global:.1f}%
                                </div>
                            </div>
                        </div>
                        <div style="display:flex;gap:20px;flex-wrap:wrap;">
                            <div style="text-align:center;padding:0 12px;">
                                <div style="font-size:28px;font-weight:800;">{total_lots}</div>
                                <div style="font-size:11px;opacity:0.7;">Total Lots</div>
                            </div>
                            <div style="text-align:center;padding:0 12px;border-left:1px solid rgba(255,255,255,0.25);">
                                <div style="font-size:28px;font-weight:800;">{n_vendu + n_reserve}</div>
                                <div style="font-size:11px;opacity:0.7;">Vendus/Réservés</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- === CARTES RESUME === -->
                <div style="display:flex;gap:14px;margin-bottom:24px;flex-wrap:wrap;">
                    <div style="flex:1;min-width:150px;background:#fff;border-radius:12px;padding:18px;border-left:5px solid #28a745;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
                        <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Disponible</div>
                        <div style="font-size:28px;font-weight:800;color:#28a745;margin-top:4px;">{n_dispo}</div>
                        <div style="font-size:11px;color:#aaa;">{(n_dispo/total_lots*100) if total_lots else 0:.0f}% du total</div>
                    </div>
                    <div style="flex:1;min-width:150px;background:#fff;border-radius:12px;padding:18px;border-left:5px solid #17a2b8;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
                        <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Pré-réservation</div>
                        <div style="font-size:28px;font-weight:800;color:#17a2b8;margin-top:4px;">{n_option}</div>
                        <div style="font-size:11px;color:#aaa;">{(n_option/total_lots*100) if total_lots else 0:.0f}% du total</div>
                    </div>
                    <div style="flex:1;min-width:150px;background:#fff;border-radius:12px;padding:18px;border-left:5px solid #e67e00;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
                        <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Réservé</div>
                        <div style="font-size:28px;font-weight:800;color:#e67e00;margin-top:4px;">{n_reserve}</div>
                        <div style="font-size:11px;color:#aaa;">{(n_reserve/total_lots*100) if total_lots else 0:.0f}% du total</div>
                    </div>
                    <div style="flex:1;min-width:150px;background:#fff;border-radius:12px;padding:18px;border-left:5px solid #6f42c1;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
                        <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Vendu</div>
                        <div style="font-size:28px;font-weight:800;color:#6f42c1;margin-top:4px;">{n_vendu}</div>
                        <div style="font-size:11px;color:#aaa;">{(n_vendu/total_lots*100) if total_lots else 0:.0f}% du total</div>
                    </div>
                </div>

                <!-- === GRAPHIQUES + CA === -->
                <div style="display:flex;gap:20px;margin-bottom:24px;flex-wrap:wrap;">

                    <!-- Graphe barres par Bloc -->
                    <div style="flex:2;min-width:300px;background:#fff;border:1px solid #e8e8e8;border-radius:12px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.04);">
                        <h4 style="margin:0 0 16px 0;font-size:15px;color:#333;">État des Lots par Bloc</h4>
                        {bar_chart_html}
                        <div style="display:flex;gap:16px;margin-top:14px;font-size:11px;flex-wrap:wrap;border-top:1px solid #f0f0f0;padding-top:10px;">
                            <span><span style="display:inline-block;width:12px;height:12px;background:#28a745;border-radius:3px;vertical-align:middle;margin-right:4px;"></span> Disponible ({n_dispo})</span>
                            <span><span style="display:inline-block;width:12px;height:12px;background:#17a2b8;border-radius:3px;vertical-align:middle;margin-right:4px;"></span> Pré-réservation ({n_option})</span>
                            <span><span style="display:inline-block;width:12px;height:12px;background:#e67e00;border-radius:3px;vertical-align:middle;margin-right:4px;"></span> Réservé ({n_reserve})</span>
                            <span><span style="display:inline-block;width:12px;height:12px;background:#6f42c1;border-radius:3px;vertical-align:middle;margin-right:4px;"></span> Vendu ({n_vendu})</span>
                        </div>
                    </div>

                    <!-- Camembert -->
                    <div style="flex:0 0 240px;background:#fff;border:1px solid #e8e8e8;border-radius:12px;padding:20px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,0.04);">
                        <h4 style="margin:0 0 16px 0;font-size:15px;color:#333;">État Global</h4>
                        <div style="width:170px;height:170px;border-radius:50%;background:{pie_gradient};margin:0 auto 16px;box-shadow:inset 0 0 0 30px white;"></div>
                        <div style="text-align:left;font-size:12px;">
                            <div style="margin:4px 0;display:flex;justify-content:space-between;">
                                <span><span style="display:inline-block;width:10px;height:10px;background:#6f42c1;border-radius:2px;margin-right:6px;"></span>Vendu</span>
                                <strong>{n_vendu}</strong>
                            </div>
                            <div style="margin:4px 0;display:flex;justify-content:space-between;">
                                <span><span style="display:inline-block;width:10px;height:10px;background:#e67e00;border-radius:2px;margin-right:6px;"></span>Réservé</span>
                                <strong>{n_reserve}</strong>
                            </div>
                            <div style="margin:4px 0;display:flex;justify-content:space-between;">
                                <span><span style="display:inline-block;width:10px;height:10px;background:#17a2b8;border-radius:2px;margin-right:6px;"></span>Pré-réservation</span>
                                <strong>{n_option}</strong>
                            </div>
                            <div style="margin:4px 0;display:flex;justify-content:space-between;">
                                <span><span style="display:inline-block;width:10px;height:10px;background:#28a745;border-radius:2px;margin-right:6px;"></span>Disponible</span>
                                <strong>{n_dispo}</strong>
                            </div>
                        </div>
                    </div>

                    <!-- CA + Réservation par type -->
                    <div style="flex:1;min-width:240px;background:#fff;border:1px solid #e8e8e8;border-radius:12px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.04);">
                        <div style="margin-bottom:20px;">
                            <div style="font-size:12px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">CA Prévisionnel</div>
                            <div style="font-size:20px;font-weight:800;color:#1a237e;margin-top:4px;">{rec._format_amount(ca_prev)}</div>
                        </div>
                        <div style="margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid #f0f0f0;">
                            <div style="font-size:12px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">CA Actuel</div>
                            <div style="font-size:20px;font-weight:800;color:#28a745;margin-top:4px;">{rec._format_amount(ca_actuel)}</div>
                        </div>
                        <h4 style="margin:0 0 14px 0;font-size:13px;color:#555;">Réservation par type</h4>
                        {type_stats_html}
                    </div>
                </div>

                <!-- === TABLEAU PAR BLOC === -->
                <div style="background:#fff;border:1px solid #e8e8e8;border-radius:12px;overflow:hidden;margin-bottom:24px;box-shadow:0 1px 4px rgba(0,0,0,0.04);">
                    <div style="background:linear-gradient(135deg,#f8f9fa,#e9ecef);padding:14px 20px;border-bottom:1px solid #e0e0e0;">
                        <h4 style="margin:0;font-size:15px;color:#333;">Statistiques par Bloc</h4>
                    </div>
                    <div style="overflow-x:auto;">
                        <table style="width:100%;border-collapse:collapse;font-size:13px;">
                            <thead>
                                <tr style="background:#fafafa;">
                                    <th style="padding:12px;text-align:left;border-bottom:2px solid #dee2e6;font-weight:700;">Bloc</th>
                                    <th style="padding:12px;text-align:center;border-bottom:2px solid #dee2e6;font-weight:700;">Total</th>
                                    <th style="padding:12px;text-align:center;border-bottom:2px solid #dee2e6;color:#28a745;font-weight:700;">Dispo.</th>
                                    <th style="padding:12px;text-align:center;border-bottom:2px solid #dee2e6;color:#17a2b8;font-weight:700;">Pré-rés.</th>
                                    <th style="padding:12px;text-align:center;border-bottom:2px solid #dee2e6;color:#e67e00;font-weight:700;">Réservé</th>
                                    <th style="padding:12px;text-align:center;border-bottom:2px solid #dee2e6;color:#6f42c1;font-weight:700;">Vendu</th>
                                    <th style="padding:12px;text-align:center;border-bottom:2px solid #dee2e6;font-weight:700;">% Vente</th>
                                    <th style="padding:12px;text-align:right;border-bottom:2px solid #dee2e6;font-weight:700;">CA Prév.</th>
                                    <th style="padding:12px;text-align:right;border-bottom:2px solid #dee2e6;font-weight:700;">CA Actuel</th>
                                </tr>
                            </thead>
                            <tbody>
                                {bloc_rows}
                                <tr style="background:#f8f9fa;font-weight:700;border-top:2px solid #dee2e6;">
                                    <td style="padding:12px;">TOTAL</td>
                                    <td style="padding:12px;text-align:center;">{total_lots}</td>
                                    <td style="padding:12px;text-align:center;color:#28a745;">{n_dispo}</td>
                                    <td style="padding:12px;text-align:center;color:#17a2b8;">{n_option}</td>
                                    <td style="padding:12px;text-align:center;color:#e67e00;">{n_reserve}</td>
                                    <td style="padding:12px;text-align:center;color:#6f42c1;">{n_vendu}</td>
                                    <td style="padding:12px;text-align:center;">
                                        <span style="background:#1a237e;color:white;padding:3px 10px;border-radius:12px;font-size:12px;">
                                            {pct_global:.1f}%
                                        </span>
                                    </td>
                                    <td style="padding:12px;text-align:right;font-size:12px;">{rec._format_amount(ca_prev)}</td>
                                    <td style="padding:12px;text-align:right;font-size:12px;">{rec._format_amount(ca_actuel)}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- === TABLEAU DETAIL PAR LOT === -->
                <div style="background:#fff;border:1px solid #e8e8e8;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.04);">
                    <div style="background:linear-gradient(135deg,#f8f9fa,#e9ecef);padding:14px 20px;border-bottom:1px solid #e0e0e0;">
                        <h4 style="margin:0;font-size:15px;color:#333;">Détail par Lot — Pourcentage de Vente</h4>
                    </div>
                    <div style="overflow-x:auto;">
                        <table style="width:100%;border-collapse:collapse;font-size:13px;">
                            <thead>
                                <tr style="background:#fafafa;">
                                    <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #dee2e6;">Client</th>
                                    <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #dee2e6;">N° Lot</th>
                                    <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #dee2e6;">Bloc</th>
                                    <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #dee2e6;">Étage</th>
                                    <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #dee2e6;">Type</th>
                                    <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #dee2e6;">Nature</th>
                                    <th style="padding:10px 12px;text-align:right;border-bottom:2px solid #dee2e6;">Surface</th>
                                    <th style="padding:10px 12px;text-align:right;border-bottom:2px solid #dee2e6;">Prix Net</th>
                                    <th style="padding:10px 12px;text-align:right;border-bottom:2px solid #dee2e6;">Payé</th>
                                    <th style="padding:10px 12px;text-align:right;border-bottom:2px solid #dee2e6;">Reste</th>
                                    <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #dee2e6;min-width:170px;">% Vente</th>
                                    <th style="padding:10px 12px;text-align:center;border-bottom:2px solid #dee2e6;">État</th>
                                </tr>
                            </thead>
                            <tbody>{lot_rows}</tbody>
                        </table>
                    </div>
                </div>
            </div>"""