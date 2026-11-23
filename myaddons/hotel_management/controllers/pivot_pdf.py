import json

from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import UnprocessableEntity

from odoo import _, http
from odoo.http import request
from odoo.http.stream import content_disposition


def _format_value(value, mtype='float', symbol=''):
    """Nombre au format français, selon le type de la mesure :
    entier « 1 234 », décimal « 1 234,50 », montant « 1 234,50 DA »."""
    if value in (None, '') or isinstance(value, bool):
        return ''
    if not isinstance(value, (int, float)):
        return str(value)
    if mtype == 'integer' and float(value).is_integer():
        text = '{:,.0f}'.format(value)
    else:
        text = '{:,.2f}'.format(value)
    text = text.replace(',', '\u202f').replace('.', ',')
    if mtype == 'monetary' and symbol:
        text = '%s %s' % (text, symbol)
    return text


class HotelPivotPdf(http.Controller):

    @http.route('/hotel/pivot/pdf', type='http', auth='user', methods=['POST'])
    def pivot_pdf(self, data, **kw):
        if not request.env.user.has_group('hotel_management.group_hotel_manager'):
            raise UnprocessableEntity(_("Accès réservé aux responsables de l'auberge."))
        table = json.load(data) if isinstance(data, FileStorage) else json.loads(data)
        if not table:
            raise UnprocessableEntity(_("Aucune donnée à imprimer"))
        types = table.get('measure_types') or []
        symbol = request.env.company.currency_id.symbol or ''
        for row in table.get('rows', []):
            for index, cell in enumerate(row.get('values', [])):
                mtype = types[index % len(types)] if types else 'float'
                cell['text'] = _format_value(cell.get('value'), mtype, symbol)
        pdf, _type = request.env['ir.actions.report']._render_qweb_pdf(
            'hotel_management.action_report_hotel_pivot', data={'table': table})
        title = table.get('report_title') or table.get('title') or 'Rapport'
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', content_disposition('%s.pdf' % title)),
        ])
