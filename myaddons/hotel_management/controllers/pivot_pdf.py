import json

from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import UnprocessableEntity

from odoo import _, fields, http
from odoo.exceptions import AccessError
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


# ----------------------------------------------------------------------
# Vue liste : impression de tous les enregistrements filtrés
# ----------------------------------------------------------------------
LIST_PDF_MODELS = {'hotel.revenue.report', 'hotel.reservation'}
LIST_PDF_LIMIT = 20000
MONTHS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
          'août', 'septembre', 'octobre', 'novembre', 'décembre']


def _group_key(record, spec):
    """(clé de tri, libellé) du groupe d'un enregistrement pour « champ » ou
    « champ:granularité »."""
    fname, _sep, gran = spec.partition(':')
    field = record._fields[fname]
    value = record[fname]
    if field.type in ('date', 'datetime'):
        if not value:
            return ((0,), _("Aucun(e)"))
        day = fields.Date.to_date(value) if field.type == 'date' else \
            fields.Datetime.context_timestamp(record, value).date()
        gran = gran or 'month'
        if gran == 'day':
            return ((1, day.toordinal()), day.strftime('%d/%m/%Y'))
        if gran == 'week':
            year, week, _wd = day.isocalendar()
            return ((1, year, week), "S%02d %s" % (week, year))
        if gran == 'quarter':
            q = (day.month - 1) // 3 + 1
            return ((1, day.year, q), "T%s %s" % (q, day.year))
        if gran == 'year':
            return ((1, day.year), str(day.year))
        return ((1, day.year, day.month), "%s %s" % (MONTHS[day.month - 1], day.year))
    if field.type == 'many2one':
        return ((1, value.display_name or '') if value else (0,),
                value.display_name if value else _("Aucun(e)"))
    if field.type == 'selection':
        labels = dict(field._description_selection(record.env))
        return ((1, str(value or '')), labels.get(value, value) or _("Aucun(e)"))
    if field.type == 'boolean':
        return ((1, bool(value)), _("Oui") if value else _("Non"))
    return ((1, str(value or '')), str(value) if value not in (False, None) else _("Aucun(e)"))


def _format_field(record, fname):
    field = record._fields[fname]
    value = record[fname]
    if field.type in ('many2one', 'many2one_reference'):
        return value.display_name if value else ''
    if field.type in ('many2many', 'one2many'):
        return ', '.join(value.mapped('display_name'))
    if field.type == 'selection':
        return dict(field._description_selection(record.env)).get(value, value) or ''
    if field.type == 'boolean':
        return _("Oui") if value else ''
    if field.type == 'date':
        return value.strftime('%d/%m/%Y') if value else ''
    if field.type == 'datetime':
        return fields.Datetime.context_timestamp(record, value).strftime('%d/%m/%Y %H:%M') if value else ''
    if field.type == 'monetary':
        currency = record[field.get_currency_field(record)] if hasattr(field, 'get_currency_field') \
            else record.env.company.currency_id
        return _format_value(value or 0.0, 'monetary', currency.symbol or '')
    if field.type == 'float':
        return _format_value(value or 0.0, 'float')
    if field.type == 'integer':
        return _format_value(value or 0, 'integer')
    if field.type in ('html', 'binary'):
        return ''
    return str(value) if value not in (False, None) else ''


def _format_total(Model, fname, total):
    field = Model._fields[fname]
    if field.type == 'monetary':
        return _format_value(total, 'monetary', Model.env.company.currency_id.symbol or '')
    return _format_value(total, 'integer' if field.type == 'integer' else 'float')


class HotelListPdf(http.Controller):

    @http.route('/hotel/list/pdf', type='http', auth='user', methods=['POST'])
    def list_pdf(self, data, **kw):
        if not request.env.user.has_group('hotel_management.group_hotel_manager'):
            raise AccessError(_("Accès réservé aux responsables de l'auberge."))
        payload = json.load(data) if isinstance(data, FileStorage) else json.loads(data)
        model = payload.get('model')
        if model not in LIST_PDF_MODELS:
            raise AccessError(_("Impression non disponible pour ce modèle."))
        Model = request.env[model]
        columns = [c for c in payload.get('columns') or [] if c.get('name') in Model._fields]
        for col in columns:
            col['numeric'] = Model._fields[col['name']].type in ('integer', 'float', 'monetary')
        group_by = [g for g in payload.get('group_by') or []
                    if g.split(':')[0] in Model._fields]
        order = payload.get('order') or None
        try:
            records = Model.search(payload.get('domain') or [], order=order, limit=LIST_PDF_LIMIT)
        except ValueError:
            records = Model.search(payload.get('domain') or [], limit=LIST_PDF_LIMIT)
        sum_fields = [c['name'] for c in columns if c.get('sum')
                      and Model._fields[c['name']].type in ('integer', 'float', 'monetary')]

        def totals(recs):
            return {f: _format_total(Model, f, sum(recs.mapped(f))) for f in sum_fields}

        rows = []

        def add(recs, level):
            if level < len(group_by):
                groups = {}
                for rec in recs:
                    key, label = _group_key(rec, group_by[level])
                    groups.setdefault(key, [label, Model.browse()])[1] |= rec
                for key in sorted(groups):
                    label, sub = groups[key]
                    rows.append({'type': 'group', 'level': level, 'label': label,
                                 'count': len(sub), 'cells': totals(sub)})
                    add(sub, level + 1)
            else:
                for rec in recs:
                    rows.append({'type': 'record', 'level': level,
                                 'cells': {c['name']: _format_field(rec, c['name']) for c in columns}})

        add(records, 0)
        values = {
            'title': payload.get('title') or Model._description,
            'filters': payload.get('filters') or [],
            'columns': columns,
            'rows': rows,
            'grand_total': totals(records) if sum_fields else {},
            'count': len(records),
            'truncated': len(records) >= LIST_PDF_LIMIT,
        }
        pdf, _type = request.env['ir.actions.report']._render_qweb_pdf(
            'hotel_management.action_report_hotel_list', data={'hotel_list': values})
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', content_disposition('%s.pdf' % values['title'])),
        ])
