import json

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestPivotPdf(HttpCase):
    """Rapports Auberge : impression PDF du tableau croisé."""

    TABLE = {
        'title': "Chiffre d'affaires", 'report_title': "CA par lit",
        'filters': ['Date : 2026'], 'measure_count': 2, 'measure_types': ['monetary', 'integer'],
        'col_group_headers': [[{'title': 'Total', 'width': 2, 'height': 1}]],
        'measure_headers': [{'title': 'Montant', 'width': 1, 'height': 1, 'is_bold': True},
                            {'title': 'Nuitées', 'width': 1, 'height': 1, 'is_bold': True}],
        'rows': [{'title': 'Total', 'indent': 0, 'values': [
                     {'value': 12345.5, 'is_bold': True}, {'value': 7, 'is_bold': True}]},
                 {'title': '101-L1', 'indent': 1, 'values': [
                     {'value': 12345.5, 'is_bold': False}, {'value': 7, 'is_bold': False}]}],
    }

    def test_render_html(self):
        table = json.loads(json.dumps(self.TABLE))
        for row in table['rows']:
            for cell in row['values']:
                from odoo.addons.hotel_management.controllers.pivot_pdf import _format_value
                cell['text'] = _format_value(cell['value'], 'float')
        html = self.env['ir.actions.report']._render_qweb_html(
            'hotel_management.action_report_hotel_pivot', None, data={'table': table})[0].decode()
        self.assertIn('CA par lit', html)
        self.assertIn('12 345,50', html)
        self.assertIn('101-L1', html)
        self.assertIn('Date : 2026', html)

    def test_pdf_route(self):
        self.authenticate('admin', 'admin')
        res = self.url_open('/hotel/pivot/pdf', data={
            'data': json.dumps(self.TABLE), 'csrf_token': self.csrf_token()}, timeout=60)
        self.assertEqual(res.status_code, 200, res.text[:500])
        self.assertEqual(res.headers['Content-Type'], 'application/pdf')
        # en mode test, Odoo renvoie le HTML au lieu de lancer wkhtmltopdf
        self.assertIn(b'CA par lit', res.content)

    def test_button_in_reports(self):
        for action in ('action_hotel_revenue_report', 'action_hotel_revenue_by_bed',
                       'action_hotel_revenue_by_source'):
            self.browser_js(
                '/odoo/action-hotel_management.%s' % action,
                "setTimeout(() => { if (document.querySelector('.o_hotel_pivot_pdf')) "
                "{ console.log('test successful'); } else { console.error('bouton PDF absent'); } }, 3000)",
                ready="!!document.querySelector('.o_pivot')", login='admin')

    def test_list_pdf_route(self):
        """Vue liste : tous les enregistrements filtrés, groupes et totaux."""
        self.authenticate('admin', 'admin')
        payload = {
            'model': 'hotel.reservation', 'domain': [], 'group_by': ['source', 'checkin:month'],
            'order': 'checkin desc', 'title': 'Performance par source', 'filters': [],
            'columns': [{'name': 'name', 'label': 'Référence', 'sum': False},
                        {'name': 'partner_id', 'label': 'Client', 'sum': False},
                        {'name': 'checkin', 'label': 'Arrivée', 'sum': False},
                        {'name': 'amount_total', 'label': 'Total', 'sum': True}],
        }
        res = self.url_open('/hotel/list/pdf', data={
            'data': json.dumps(payload), 'csrf_token': self.csrf_token()}, timeout=60)
        self.assertEqual(res.status_code, 200, res.text[:500])
        self.assertIn(b'Performance par source', res.content)
        self.assertIn(b'Total', res.content)
        # Modèle non autorisé : refusé
        payload['model'] = 'res.users'
        res = self.url_open('/hotel/list/pdf', data={
            'data': json.dumps(payload), 'csrf_token': self.csrf_token()}, timeout=60)
        self.assertNotEqual(res.status_code, 200)

    def test_list_button_in_reports(self):
        for action in ('action_hotel_revenue_report', 'action_hotel_revenue_by_bed',
                       'action_hotel_revenue_by_source'):
            self.browser_js(
                '/odoo/action-hotel_management.%s?view_type=list' % action,
                "setTimeout(() => { if (document.querySelector('.o_hotel_list_pdf')) "
                "{ console.log('test successful'); } else { console.error('bouton PDF liste absent'); } }, 3000)",
                ready="!!document.querySelector('.o_list_view')", login='admin')
