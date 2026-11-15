from odoo import fields, models, tools

JOURNAL_KINDS = [
    ('payment', 'Paiement client'),
    ('refund', 'Remboursement client'),
    ('purchase', 'Achat / paiement fournisseur'),
    ('purchase_refund', 'Remboursement fournisseur'),
    ('in', 'Entrée'),
    ('out', 'Sortie'),
    ('expense', 'Dépense'),
    ('transfer', 'Transfert'),
]


class CaisseJournal(models.Model):
    """Journal de caisse unifié (cahier des charges §9) : TOUT ce qui entre
    dans la caisse ou en sort, sur une seule liste — paiements clients en
    espèces rattachés à une caisse + entrées / sorties / dépenses / transferts.
    Vue SQL en lecture seule."""
    _name = 'caisse.journal'
    _description = "Journal de caisse"
    _auto = False
    _order = 'date desc, id desc'
    _rec_name = 'label'
    # Tables lues par la vue : l'ORM enregistre les modifications en attente
    # avant toute lecture du journal (sinon une opération juste saisie manque).
    _depends = {
        'account.payment': [
            'caisse_session_id', 'state', 'date', 'payment_type', 'partner_type', 'memo', 'name',
            'partner_id', 'hotel_reservation_id', 'amount_company_currency_signed',
            'company_id', 'create_uid',
        ],
        'caisse.move': [
            'date', 'session_id', 'move_type', 'reason', 'partner_id', 'reference',
            'amount', 'signed_amount', 'user_id', 'company_id', 'attachment',
        ],
    }

    date = fields.Datetime(string="Date", readonly=True)
    day = fields.Date(string="Jour", readonly=True)
    session_id = fields.Many2one('caisse.session', string="Caisse", readonly=True)
    kind = fields.Selection(JOURNAL_KINDS, string="Opération", readonly=True)
    label = fields.Char(string="Libellé", readonly=True)
    partner_id = fields.Many2one('res.partner', string="Client / tiers", readonly=True)
    reservation_id = fields.Many2one(
        'hotel.reservation', string="Réservation", readonly=True)
    reference = fields.Char(string="Référence", readonly=True)
    amount_in = fields.Monetary(string="Entrée", readonly=True)
    amount_out = fields.Monetary(string="Sortie", readonly=True)
    amount = fields.Monetary(string="Montant (+/-)", readonly=True)
    user_id = fields.Many2one('res.users', string="Saisi par", readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    payment_id = fields.Many2one('account.payment', string="Paiement", readonly=True)
    move_id = fields.Many2one('caisse.move', string="Mouvement", readonly=True)
    has_attachment = fields.Boolean(string="Justificatif joint", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Ids : paiements en positif pair, mouvements en impair (uniques).
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    p.id * 2 AS id,
                    COALESCE(p.create_date, p.date::timestamp) AS date,
                    p.date AS day,
                    p.caisse_session_id AS session_id,
                    CASE
                        WHEN p.partner_type = 'supplier' AND p.payment_type = 'outbound' THEN 'purchase'
                        WHEN p.partner_type = 'supplier' THEN 'purchase_refund'
                        WHEN p.payment_type = 'outbound' THEN 'refund'
                        ELSE 'payment'
                    END AS kind,
                    COALESCE(NULLIF(p.memo, ''), p.name) AS label,
                    p.partner_id,
                    p.hotel_reservation_id AS reservation_id,
                    p.name AS reference,
                    GREATEST(p.amount_company_currency_signed, 0) AS amount_in,
                    GREATEST(-p.amount_company_currency_signed, 0) AS amount_out,
                    p.amount_company_currency_signed AS amount,
                    p.create_uid AS user_id,
                    p.company_id,
                    c.currency_id,
                    p.id AS payment_id,
                    NULL::integer AS move_id,
                    FALSE AS has_attachment
                FROM account_payment p
                JOIN res_company c ON c.id = p.company_id
                WHERE p.caisse_session_id IS NOT NULL
                  AND p.state IN ('paid', 'reconciled')
                UNION ALL
                SELECT
                    m.id * 2 + 1 AS id,
                    m.date,
                    m.date::date AS day,
                    m.session_id,
                    m.move_type AS kind,
                    m.reason AS label,
                    m.partner_id,
                    NULL::integer AS reservation_id,
                    m.reference,
                    CASE WHEN m.move_type = 'in' THEN m.amount ELSE 0 END AS amount_in,
                    CASE WHEN m.move_type = 'in' THEN 0 ELSE m.amount END AS amount_out,
                    m.signed_amount AS amount,
                    m.user_id,
                    m.company_id,
                    c.currency_id,
                    NULL::integer AS payment_id,
                    m.id AS move_id,
                    EXISTS (
                        SELECT 1 FROM ir_attachment a
                        WHERE a.res_model = 'caisse.move' AND a.res_id = m.id
                          AND a.res_field = 'attachment'
                    ) AS has_attachment
                FROM caisse_move m
                JOIN res_company c ON c.id = m.company_id
            )
        """)

    def action_open_source(self):
        """Ouvre le paiement ou le mouvement d'origine."""
        self.ensure_one()
        record = self.payment_id or self.move_id
        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'res_id': record.id,
            'views': [(False, 'form')],
            'target': 'current',
        }
