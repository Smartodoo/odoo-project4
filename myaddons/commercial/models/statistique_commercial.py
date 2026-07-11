from odoo import models, fields, api


class CommercialStatistiqueCommercial(models.Model):
    _name = 'commercial.statistique.commercial'
    _description = 'Statistique par Commercial'

    name = fields.Char(string="Nom", compute='_compute_name', store=True)
    commercial_id = fields.Many2one(
        'res.users', string="Commercial",
        domain=lambda self: [('groups_id', 'in', [self.env.ref('commercial.group_commercial_user').id])],
    )
    date_du = fields.Date(string="Du")
    date_au = fields.Date(string="Au")

    # Summary fields
    total_clients = fields.Integer(string="Clients", compute='_compute_stats', store=False)
    total_lots_vendus = fields.Integer(string="Lots vendus", compute='_compute_stats', store=False)
    ca_total = fields.Float(string="CA Total", compute='_compute_stats', store=False)
    ca_encaisse = fields.Float(string="CA Encaissé", compute='_compute_stats', store=False)
    reste_a_payer = fields.Float(string="Reste à payer", compute='_compute_stats', store=False)

    # Dashboard
    dashboard_html = fields.Html(string="Tableau de Bord", compute='_compute_dashboard', sanitize=False)

    @api.depends('commercial_id')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.commercial_id.name or 'Nouveau'

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

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

    def _get_lot_total_paid(self, lot):
        """Retourne le montant total payé sur un lot (tous paiements confondus)."""
        total = 0
        for v in lot.versement_ids:
            if v.state == 'confirme':
                total += v.montant
            elif v.state == 'partiellement_rembourse':
                total += v.montant_restant
        for p in lot.paiement_ids:
            for e in p.echeance_ids:
                if e.etat == 'paye':
                    total += e.montant
            if hasattr(p, 'echeance_apport_ids'):
                for e in p.echeance_apport_ids:
                    if e.etat == 'paye':
                        total += e.montant
        return total

    def _get_lot_first_sale(self, lot):
        """Retourne (user, date, client) de la première transaction confirmée sur le lot.
        Le commercial est l'utilisateur qui a confirmé le premier versement ou la première échéance."""
        candidates = []
        # Versements confirmés
        for v in lot.versement_ids.filtered(lambda v: v.state in ('confirme', 'partiellement_rembourse', 'totalement_rembourse') and v.date_encaissement):
            user = v.caisse_entry_id.user_id if v.caisse_entry_id else False
            if user:
                candidates.append((v.date_encaissement, user, v.client_id))
        # Échéances payées
        for p in lot.paiement_ids:
            for e in p.echeance_ids.filtered(lambda e: e.etat == 'paye' and e.date_encaissement):
                user = e.caisse_entry_id.user_id if e.caisse_entry_id else False
                if user:
                    candidates.append((e.date_encaissement, user, p.client_id))
            if hasattr(p, 'echeance_apport_ids'):
                for e in p.echeance_apport_ids.filtered(lambda e: e.etat == 'paye' and e.date_encaissement):
                    user = e.caisse_entry_id.user_id if e.caisse_entry_id else False
                    if user:
                        candidates.append((e.date_encaissement, user, p.client_id))
        if not candidates:
            return False, False, False
        candidates.sort(key=lambda c: c[0])
        return candidates[0][1], candidates[0][0], candidates[0][2]

    def _get_commercial_data(self):
        """Retourne les lots vendus par le commercial sélectionné.
        Le commercial d'un lot est l'utilisateur qui a confirmé le premier versement
        ou la première échéance (via caisse_entry_id.user_id)."""
        self.ensure_one()
        if not self.commercial_id:
            return {}

        commercial_uid = self.commercial_id.id

        # Collecter les lots candidats : lots ayant au moins une transaction par ce commercial
        candidate_lot_ids = set()

        versements = self.env['commercial.versement'].sudo().search([
            ('state', 'in', ('confirme', 'partiellement_rembourse', 'totalement_rembourse')),
            ('caisse_entry_id.user_id', '=', commercial_uid),
        ])
        candidate_lot_ids.update(versements.mapped('lot_id').ids)

        echeances = self.env['commercial.echeance'].sudo().search([
            ('etat', '=', 'paye'),
            ('caisse_entry_id.user_id', '=', commercial_uid),
        ])
        candidate_lot_ids.update(echeances.mapped('lot_id').ids)

        echeances_apport = self.env['commercial.echeance.apport'].sudo().search([
            ('etat', '=', 'paye'),
            ('caisse_entry_id.user_id', '=', commercial_uid),
        ])
        candidate_lot_ids.update(echeances_apport.mapped('paiement_id.lot_id').ids)

        empty_data = {
            'total_clients': 0, 'total_lots': 0,
            'ca_total': 0.0, 'ca_encaisse': 0.0, 'reste_a_payer': 0.0,
            'by_projet': {},
        }
        if not candidate_lot_ids:
            return empty_data

        lots = self.env['commercial.lot'].sudo().browse(list(candidate_lot_ids))

        state_map = {
            'disponible': 'Disponible',
            'en_option': 'Pré-réservation',
            'reserve': 'Réservé',
            'vendu': 'Vendu',
        }

        data = {
            'total_clients': 0,
            'total_lots': 0,
            'ca_total': 0.0,
            'ca_encaisse': 0.0,
            'by_projet': {},
        }
        seen_clients = set()

        for lot in lots:
            first_user, first_date, first_client = self._get_lot_first_sale(lot)
            # Vérifier que la PREMIÈRE transaction est bien par ce commercial
            if not first_user or first_user.id != commercial_uid:
                continue
            # Filtrer par date de première vente
            if self.date_du and first_date and first_date < self.date_du:
                continue
            if self.date_au and first_date and first_date > self.date_au:
                continue

            partner = first_client
            if partner:
                seen_clients.add(partner.id)

            # Remise spécifique au contact
            line = self.env['commercial.partner.lot'].sudo().search([
                ('partner_id', '=', partner.id if partner else False),
                ('lot_id', '=', lot.id),
            ], limit=1)
            remise = line.remise if line else 0.0
            montant_net = lot.montant_global - remise
            paid = self._get_lot_total_paid(lot)
            reste = montant_net - paid
            pct = min((paid / montant_net * 100), 100) if montant_net > 0 else 0

            data['total_lots'] += 1
            data['ca_total'] += montant_net
            data['ca_encaisse'] += paid

            row = {
                'client': partner.name if partner else '',
                'bloc': lot.bloc_id.code or '',
                'lot': lot.numero_lot or '',
                'etage': lot.etage_id.name or '',
                'montant': montant_net,
                'paid': paid,
                'reste': reste,
                'pct': pct,
                'state': state_map.get(lot.state, lot.state or ''),
                'state_key': lot.state,
            }

            pname = lot.projet_id.name or 'Sans projet'
            if pname not in data['by_projet']:
                data['by_projet'][pname] = {
                    'lots': 0, 'ca': 0.0, 'paid': 0.0,
                    'clients': {},
                }
            proj = data['by_projet'][pname]
            proj['lots'] += 1
            proj['ca'] += montant_net
            proj['paid'] += paid

            cname = partner.name if partner else ''
            if cname not in proj['clients']:
                proj['clients'][cname] = []
            proj['clients'][cname].append(row)

        data['total_clients'] = len(seen_clients)
        data['reste_a_payer'] = data['ca_total'] - data['ca_encaisse']
        return data

    def action_print(self):
        self.ensure_one()
        return self.env.ref('commercial.action_report_statistique_commercial').report_action(self)

    # -------------------------------------------------------------------------
    # Computed: summary
    # -------------------------------------------------------------------------

    @api.depends('commercial_id', 'date_du', 'date_au')
    def _compute_stats(self):
        for rec in self:
            if not rec.commercial_id:
                rec.total_clients = rec.total_lots_vendus = 0
                rec.ca_total = rec.ca_encaisse = rec.reste_a_payer = 0
                continue
            data = rec._get_commercial_data()
            rec.total_clients = data.get('total_clients', 0)
            rec.total_lots_vendus = data.get('total_lots', 0)
            rec.ca_total = data.get('ca_total', 0)
            rec.ca_encaisse = data.get('ca_encaisse', 0)
            rec.reste_a_payer = data.get('reste_a_payer', 0)

    # -------------------------------------------------------------------------
    # Computed: Dashboard HTML
    # -------------------------------------------------------------------------

    @api.depends('commercial_id', 'date_du', 'date_au')
    def _compute_dashboard(self):
        for rec in self:
            if not rec.commercial_id:
                rec.dashboard_html = (
                    '<div style="text-align:center;padding:60px;color:#999;">'
                    '<h3>Sélectionnez un commercial pour afficher les statistiques</h3></div>'
                )
                continue

            data = rec._get_commercial_data()
            total_clients = data['total_clients']
            total_lots = data['total_lots']
            ca_total = data['ca_total']
            ca_encaisse = data['ca_encaisse']
            reste = data['reste_a_payer']
            pct_global = (ca_encaisse / ca_total * 100) if ca_total > 0 else 0

            # --- Detail sections grouped by projet ---
            by_projet = data['by_projet']
            projet_sections_html = ""
            state_styles = {
                'disponible': ('#d4edda', '#155724'),
                'en_option': ('#d1ecf1', '#0c5460'),
                'reserve': ('#fff3cd', '#856404'),
                'vendu': ('#e8daef', '#4a235a'),
            }

            for pname, pdata in by_projet.items():
                p_ca = pdata['ca']
                p_paid = pdata['paid']
                p_reste = p_ca - p_paid
                p_pct = (p_paid / p_ca * 100) if p_ca > 0 else 0
                p_nb_clients = len(pdata['clients'])

                # Build client rows for this project
                client_rows = ""
                for cname, rows in pdata['clients'].items():
                    first = True
                    client_lot_count = len(rows)
                    for row in rows:
                        pct = row['pct']
                        if pct >= 75:
                            bar_color = '#28a745'
                        elif pct >= 50:
                            bar_color = '#17a2b8'
                        elif pct >= 25:
                            bar_color = '#e67e00'
                        else:
                            bar_color = '#dc3545'
                        bg, fg = state_styles.get(row['state_key'], ('#e2e3e5', '#383d41'))

                        client_cell = ""
                        if first:
                            client_cell = f'<td style="padding:8px 12px;font-weight:600;vertical-align:top;border-right:1px solid #f0f0f0;" rowspan="{client_lot_count}">{cname}</td>'
                            first = False

                        client_rows += f"""
                        <tr style="border-bottom:1px solid #f0f0f0;">
                            {client_cell}
                            <td style="padding:8px 12px;">{row['bloc']}</td>
                            <td style="padding:8px 12px;">{row['etage']}</td>
                            <td style="padding:8px 12px;">{row['lot']}</td>
                            <td style="padding:8px 12px;text-align:right;font-size:12px;">{rec._format_amount(row['montant'])}</td>
                            <td style="padding:8px 12px;text-align:right;font-size:12px;color:#28a745;font-weight:600;">{rec._format_amount(row['paid'])}</td>
                            <td style="padding:8px 12px;text-align:right;font-size:12px;color:#dc3545;">{rec._format_amount(row['reste'])}</td>
                            <td style="padding:8px 12px;min-width:140px;">
                                <div style="display:flex;align-items:center;gap:6px;">
                                    <div style="flex:1;background:#e9ecef;border-radius:6px;height:18px;min-width:60px;overflow:hidden;">
                                        <div style="width:{pct:.0f}%;height:100%;background:{bar_color};border-radius:6px;"></div>
                                    </div>
                                    <span style="font-weight:700;font-size:12px;min-width:42px;text-align:right;">{pct:.1f}%</span>
                                </div>
                            </td>
                            <td style="padding:8px 12px;text-align:center;">
                                <span style="background:{bg};color:{fg};padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;white-space:nowrap;">
                                    {row['state']}
                                </span>
                            </td>
                        </tr>"""

                # Sous-total row for this project
                sub_bar_color = '#28a745' if p_pct >= 75 else '#17a2b8' if p_pct >= 50 else '#e67e00' if p_pct >= 25 else '#dc3545'
                subtotal_row = f"""
                <tr style="background:#f8f9fa;font-weight:700;border-top:2px solid #dee2e6;">
                    <td colspan="4" style="padding:10px 12px;font-size:12px;">Sous-total — {pdata['lots']} lots, {p_nb_clients} client{'s' if p_nb_clients > 1 else ''}</td>
                    <td style="padding:10px 12px;text-align:right;font-size:12px;">{rec._format_amount(p_ca)}</td>
                    <td style="padding:10px 12px;text-align:right;font-size:12px;color:#28a745;">{rec._format_amount(p_paid)}</td>
                    <td style="padding:10px 12px;text-align:right;font-size:12px;color:#dc3545;">{rec._format_amount(p_reste)}</td>
                    <td style="padding:10px 12px;">
                        <div style="display:flex;align-items:center;gap:6px;">
                            <div style="flex:1;background:#e9ecef;border-radius:6px;height:18px;min-width:60px;overflow:hidden;">
                                <div style="width:{p_pct:.0f}%;height:100%;background:{sub_bar_color};border-radius:6px;"></div>
                            </div>
                            <span style="font-weight:700;font-size:12px;">{p_pct:.1f}%</span>
                        </div>
                    </td>
                    <td></td>
                </tr>"""

                projet_sections_html += f"""
                <div style="background:#fff;border:1px solid #e8e8e8;border-radius:12px;overflow:hidden;margin-bottom:20px;box-shadow:0 1px 4px rgba(0,0,0,0.04);">
                    <div style="background:linear-gradient(135deg,#1a237e,#283593);padding:12px 20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;">
                        <h4 style="margin:0;font-size:15px;color:#fff;font-weight:700;">{pname}</h4>
                        <div style="display:flex;gap:16px;align-items:center;">
                            <span style="font-size:12px;color:rgba(255,255,255,0.8);">{pdata['lots']} lots</span>
                            <span style="font-size:12px;color:rgba(255,255,255,0.8);">{p_nb_clients} client{'s' if p_nb_clients > 1 else ''}</span>
                            <span style="background:rgba(255,255,255,0.2);color:white;padding:3px 12px;border-radius:12px;font-size:12px;font-weight:700;">{p_pct:.1f}%</span>
                        </div>
                    </div>
                    <div style="overflow-x:auto;">
                        <table style="width:100%;border-collapse:collapse;font-size:13px;">
                            <thead>
                                <tr style="background:#fafafa;">
                                    <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #dee2e6;">Client</th>
                                    <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #dee2e6;">Bloc</th>
                                    <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #dee2e6;">Étage</th>
                                    <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #dee2e6;">Lot</th>
                                    <th style="padding:10px 12px;text-align:right;border-bottom:2px solid #dee2e6;">Montant</th>
                                    <th style="padding:10px 12px;text-align:right;border-bottom:2px solid #dee2e6;">Payé</th>
                                    <th style="padding:10px 12px;text-align:right;border-bottom:2px solid #dee2e6;">Reste</th>
                                    <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #dee2e6;min-width:150px;">% Paiement</th>
                                    <th style="padding:10px 12px;text-align:center;border-bottom:2px solid #dee2e6;">État</th>
                                </tr>
                            </thead>
                            <tbody>
                                {client_rows}
                                {subtotal_row}
                            </tbody>
                        </table>
                    </div>
                </div>"""

            # --- Bar chart by projet ---
            max_ca = max((v['ca'] for v in by_projet.values()), default=1) or 1
            bar_chart_html = ""
            for pname, pdata in by_projet.items():
                bar_w = pdata['ca'] / max_ca * 100
                p_pct = (pdata['paid'] / pdata['ca'] * 100) if pdata['ca'] > 0 else 0
                paid_w = pdata['paid'] / max_ca * 100
                bar_chart_html += f"""
                <div style="display:flex;align-items:center;margin-bottom:8px;">
                    <div style="width:120px;font-size:12px;font-weight:600;text-align:right;padding-right:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{pname}</div>
                    <div style="flex:1;position:relative;height:30px;background:#f5f5f5;border-radius:6px;overflow:hidden;">
                        <div style="width:{bar_w:.1f}%;height:100%;background:#e0e0e0;border-radius:6px;position:absolute;top:0;left:0;"></div>
                        <div style="width:{paid_w:.1f}%;height:100%;background:#28a745;border-radius:6px;position:absolute;top:0;left:0;display:flex;align-items:center;justify-content:center;color:white;font-size:10px;font-weight:600;">
                            {p_pct:.0f}%
                        </div>
                    </div>
                    <div style="width:50px;font-size:11px;text-align:center;font-weight:600;padding-left:6px;">{pdata['lots']} lots</div>
                </div>"""

            # =====================================================================
            # HTML COMPLET
            # =====================================================================
            rec.dashboard_html = f"""
            <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:1400px;">

                <!-- === EN-TETE === -->
                <div style="background:linear-gradient(135deg,#1a237e,#3949ab);color:white;padding:24px;border-radius:14px;margin-bottom:24px;">
                    <h2 style="margin:0 0 16px 0;font-size:24px;letter-spacing:0.5px;">{rec.commercial_id.name or ''}</h2>
                    <div style="display:flex;align-items:center;gap:24px;flex-wrap:wrap;">
                        <div style="flex:1;min-width:250px;">
                            <div style="font-size:12px;opacity:0.8;margin-bottom:6px;">Encaissement Global</div>
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
                                <div style="font-size:28px;font-weight:800;">{total_clients}</div>
                                <div style="font-size:11px;opacity:0.7;">Clients</div>
                            </div>
                            <div style="text-align:center;padding:0 12px;border-left:1px solid rgba(255,255,255,0.25);">
                                <div style="font-size:28px;font-weight:800;">{total_lots}</div>
                                <div style="font-size:11px;opacity:0.7;">Lots</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- === CARTES RESUME === -->
                <div style="display:flex;gap:14px;margin-bottom:24px;flex-wrap:wrap;">
                    <div style="flex:1;min-width:150px;background:#fff;border-radius:12px;padding:18px;border-left:5px solid #17a2b8;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
                        <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Clients</div>
                        <div style="font-size:28px;font-weight:800;color:#17a2b8;margin-top:4px;">{total_clients}</div>
                    </div>
                    <div style="flex:1;min-width:150px;background:#fff;border-radius:12px;padding:18px;border-left:5px solid #6f42c1;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
                        <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Lots</div>
                        <div style="font-size:28px;font-weight:800;color:#6f42c1;margin-top:4px;">{total_lots}</div>
                    </div>
                    <div style="flex:1;min-width:150px;background:#fff;border-radius:12px;padding:18px;border-left:5px solid #28a745;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
                        <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">CA Encaissé</div>
                        <div style="font-size:20px;font-weight:800;color:#28a745;margin-top:4px;">{rec._format_amount(ca_encaisse)}</div>
                    </div>
                    <div style="flex:1;min-width:150px;background:#fff;border-radius:12px;padding:18px;border-left:5px solid #dc3545;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
                        <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Reste à payer</div>
                        <div style="font-size:20px;font-weight:800;color:#dc3545;margin-top:4px;">{rec._format_amount(reste)}</div>
                    </div>
                </div>

                <!-- === GRAPHIQUE PAR PROJET === -->
                <div style="background:#fff;border:1px solid #e8e8e8;border-radius:12px;padding:20px;margin-bottom:24px;box-shadow:0 1px 4px rgba(0,0,0,0.04);">
                    <h4 style="margin:0 0 16px 0;font-size:15px;color:#333;">Répartition par Projet</h4>
                    {bar_chart_html if bar_chart_html else '<div style="text-align:center;padding:20px;color:#999;">Aucune donnée</div>'}
                    <div style="display:flex;gap:16px;margin-top:14px;font-size:11px;flex-wrap:wrap;border-top:1px solid #f0f0f0;padding-top:10px;">
                        <span><span style="display:inline-block;width:12px;height:12px;background:#28a745;border-radius:3px;vertical-align:middle;margin-right:4px;"></span> Encaissé</span>
                        <span><span style="display:inline-block;width:12px;height:12px;background:#e0e0e0;border-radius:3px;vertical-align:middle;margin-right:4px;"></span> CA Total</span>
                    </div>
                </div>

                <!-- === DETAIL PAR PROJET === -->
                {projet_sections_html if projet_sections_html else '<div style="background:#fff;border:1px solid #e8e8e8;border-radius:12px;padding:30px;text-align:center;color:#999;">Aucun lot trouvé pour ce commercial</div>'}

                <!-- === TOTAL GLOBAL === -->
                {f'''<div style="background:linear-gradient(135deg,#1a237e,#3949ab);color:white;padding:18px 24px;border-radius:12px;margin-top:4px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
                        <div style="font-size:16px;font-weight:700;">TOTAL GLOBAL</div>
                        <div style="display:flex;gap:24px;flex-wrap:wrap;align-items:center;">
                            <div style="text-align:center;">
                                <div style="font-size:11px;opacity:0.7;">CA Total</div>
                                <div style="font-size:16px;font-weight:800;">{rec._format_amount(ca_total)}</div>
                            </div>
                            <div style="text-align:center;">
                                <div style="font-size:11px;opacity:0.7;">Encaissé</div>
                                <div style="font-size:16px;font-weight:800;color:#81c784;">{rec._format_amount(ca_encaisse)}</div>
                            </div>
                            <div style="text-align:center;">
                                <div style="font-size:11px;opacity:0.7;">Reste</div>
                                <div style="font-size:16px;font-weight:800;color:#ef9a9a;">{rec._format_amount(reste)}</div>
                            </div>
                            <div style="background:rgba(255,255,255,0.2);padding:6px 16px;border-radius:12px;font-weight:800;font-size:15px;">{pct_global:.1f}%</div>
                        </div>
                    </div>
                </div>''' if projet_sections_html else ''}
            </div>"""
