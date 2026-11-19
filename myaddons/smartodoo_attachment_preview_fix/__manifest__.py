{
    'name': 'Smartodoo Attachment Preview Fix',
    'summary': 'Honour the invisible condition of the form attachment preview',
    'description': """
        Odoo 20's mail form compiler overwrites the t-if of
        <div class="o_attachment_preview" invisible="..."/>, so the preview
        (and the COMBO layout moving the chatter to the bottom) is shown even
        when the view says it must be hidden, e.g. on posted invoices.
        This module feeds the real visibility of the preview into the layout
        computation, so a hidden preview gives the normal chatter layout.
    """,
    'version': '20.0.1.0.0',
    'category': 'Hidden',
    'license': 'LGPL-3',
    'author': 'Smartodoo',
    'depends': ['mail'],
    'assets': {
        'web.assets_backend': [
            'smartodoo_attachment_preview_fix/static/src/views/form/form_compiler.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
