# Copyright 2015 ABF OSIELL <https://osiell.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "sinistre",
    'version': '20.0.1.0.0',
    "author": "hamitouche younes",
    'description': '',
    "category": "Tools",
    "license": "AGPL-3",
    "depends": ['hr', 'fleet', 'base', 'contacts', ],
    "data": [

        'wizard/print_report_accident_date.xml',
        'report/sinistre_report_template.xml',
        'report/constat_report_template.xml',
        'views/sinistre.xml',
        'security/ir.access.csv',

    ],

    "application": True,
    "installable": True,
    'auto_install': False,
    'icon': 'sinistre/static/description/icon.png',
}
