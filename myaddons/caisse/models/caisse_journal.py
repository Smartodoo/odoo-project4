from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

JOURNAL_KINDS = [
    ('payment', 'Paiement client'),
    ('refund', 'Remboursement client'),
    ('purchase', 'Achat fournisseur'),
    ('purchase_refund', 'Remboursement fournisseur'),
    ('expense_note', 'Note de frais'),
    ('in', 'Entrée'),
    ('out', 'Sortie'),
    ('expense', 'Dépense (saisie libre)'),
    ('transfer', 'Transfert'),
]

# Classement du menu Caisse (cahier des charges) :
#   Entrées  : paiements des réservations, entrées saisies (fond de départ…),
#              remboursements reçus des fournisseurs ;
#   Dépenses : notes de frais et achats ;
#   Sorties  : remboursements clients, sorties et transferts.
JOURNAL_CATEGORIES = [
    ('in', 'Entrée'),
    ('expense', 'Dépense'),
    ('out', 'Sortie'),
]
KIND_CATEGORY = {
    'payment': 'in', 'in': 'in', 'purchase_refund': 'in',
    'expense_note': 'expense', 'purchase': 'expense', 'expense': 'expense',
    'refund': 'out', 'out': 'out', 'transfer': 'out',
}


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
            'caisse_session_id', 'caisse_kind', 'state', 'date', 'payment_type',
            'partner_type', 'memo', 'name',
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
    category = fields.Selection(JOURNAL_CATEGORIES, string="Catégorie", readonly=True)
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
                    p.kind,
                    CASE p.kind WHEN 'payment' THEN 'in' WHEN 'in' THEN 'in' WHEN 'purchase_refund' THEN 'in' WHEN 'expense_note' THEN 'expense' WHEN 'purchase' THEN 'expense' WHEN 'expense' THEN 'expense' ELSE 'out' END AS category,
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
                FROM (
                    SELECT pay.*, COALESCE(pay.caisse_kind, CASE
                        WHEN pay.partner_type = 'supplier' AND pay.payment_type = 'outbound' THEN 'purchase'
                        WHEN pay.partner_type = 'supplier' THEN 'purchase_refund'
                        WHEN pay.payment_type = 'outbound' THEN 'refund'
                        ELSE 'payment'
                    END) AS kind
                    FROM account_payment pay
                ) p
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
                    CASE m.move_type WHEN 'payment' THEN 'in' WHEN 'in' THEN 'in' WHEN 'purchase_refund' THEN 'in' WHEN 'expense_note' THEN 'expense' WHEN 'purchase' THEN 'expense' WHEN 'expense' THEN 'expense' ELSE 'out' END AS category,
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
        """Ouvre l'opération d'origine : note de frais, facture d'achat,
        paiement ou mouvement de caisse."""
        self.ensure_one()
        payment = self.payment_id.sudo()
        record = (payment.expense_ids or payment.reconciled_bill_ids.expense_ids
                  or payment.reconciled_bill_ids[:1]).sudo(False) if payment else False
        record = record or self.payment_id or self.move_id
        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'res_id': record.id,
            'views': [(False, 'form')],
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Boutons « Nouveau » des menus Entrées et Sorties (les notes de frais
    # et les achats se créent dans leurs applications, pas dans la caisse)
    # ------------------------------------------------------------------
    @api.model
    def _caisse_open_session(self):
        session = self.env['caisse.session']._get_open_session()
        if not session:
            raise UserError(_(
                "Aucune caisse n'est ouverte : ouvrez la caisse du jour "
                "(menu Caisse du jour) avant d'enregistrer une opération."))
        return session

    def action_caisse_new_in(self):
        return self._caisse_open_session().action_new_in()

    def action_caisse_new_out(self):
        return self._caisse_open_session().action_new_out()

    def action_caisse_new_transfer(self):
        return self._caisse_open_session().action_new_transfer()
