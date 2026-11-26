from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, HttpCase, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReceptionRules(TransactionCase):
    """Remboursement à part, remise client supprimée, chambres / lits déjà
    pris non proposés (même en brouillon), envoi groupé des confirmations."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))
        cls.ci = fields.Date.today() + timedelta(days=950)
        cls.co = cls.ci + timedelta(days=2)
        rtype = cls.env['hotel.room.type'].create({'name': 'Type règles', 'room_price': 3000})
        cls.room = cls.env['hotel.room'].create({
            'name': 'RR-1', 'capacity': 2})
        cls.dorm = cls.env['hotel.room'].create({
            'name': 'RR-D', 'capacity': 3})
        cls.partner = cls.env['res.partner'].create({
            'name': 'Client règles', 'email': 'regles@example.com',
            'hotel_last_name': 'Regles', 'hotel_first_name': 'Client', 'phone': '0550000008',
            'street': '1 rue Test', 'hotel_id_type': 'cni', 'hotel_id_number': 'ID-R',
            'hotel_birthdate': '1990-01-01'})

    def _resa(self, **vals):
        values = {'partner_id': self.partner.id, 'checkin': self.ci, 'checkout': self.co,
                  'line_ids': [(0, 0, {'room_id': self.room.id, 'price_unit': 3000})]}
        values.update(vals)
        return self.env['hotel.reservation'].create(values)

    # --- Remboursement : bouton à part ------------------------------------
    def test_refund_separate_button(self):
        resa = self._resa()
        # Encaisser : le type ne propose que Acompte / Paiement
        wizard_form = Form(self.env['hotel.reservation.payment.wizard'].with_context(
            **resa.action_register_hotel_payment()['context']))
        selection = dict(self.env['hotel.reservation.payment.wizard']._fields[
            'encaisse_kind'].selection)
        self.assertEqual(set(selection), {'deposit', 'payment'})
        self.assertEqual(wizard_form.encaisse_kind, 'deposit')
        # Rembourser : impossible tant qu'aucun paiement n'est validé
        self.assertEqual(resa.amount_paid, 0)
        with self.assertRaises(UserError):
            resa.action_refund_hotel_payment()
        view = self.env.ref('hotel_management.view_hotel_reservation_form').arch
        self.assertIn('name="action_refund_hotel_payment"', view)
        self.assertIn('invisible="amount_paid &lt;= 0"', view)
        # Paiement validé (carte) -> remboursement possible, en mode « refund »
        wizard = self.env['hotel.reservation.payment.wizard'].create({
            'reservation_id': resa.id, 'payment_mode': 'card', 'amount': 2000,
            'encaisse_kind': 'payment'})
        self.assertEqual(wizard.payment_kind, 'payment')
        # TPE : les informations de la carte sont obligatoires
        with self.assertRaises(UserError):
            wizard.action_confirm()
        wizard.write({'card_type': 'visa', 'card_last_name': 'Benali',
                      'card_first_name': 'Amine', 'card_number': '4111 1111 1111 1234',
                      'card_expiry': '01/20'})
        with self.assertRaises(ValidationError):  # carte expirée
            wizard.action_confirm()
        wizard.card_expiry = '8/99'
        wizard.action_confirm()
        self.assertEqual(resa.amount_paid, 2000)
        payment = resa.payment_ids.filtered(lambda p: p.payment_type == 'inbound')
        self.assertEqual(payment.hotel_card_type, 'visa')
        self.assertEqual(payment.hotel_card_number, '**** **** **** 1234')
        self.assertEqual(payment.hotel_card_expiry, '08/99')
        self.assertEqual(payment.hotel_card_last_name, 'Benali')

        ctx = resa.action_refund_hotel_payment()['context']
        refund = self.env['hotel.reservation.payment.wizard'].with_context(**ctx).create({
            'reservation_id': resa.id, 'payment_mode': 'card', 'amount': 500})
        self.assertEqual(refund.payment_kind, 'refund')
        self.assertFalse(refund.encaisse_kind)
        refund.action_confirm()
        self.assertEqual(resa.amount_paid, 1500)

    # --- Virement / chèque : banque + numéro --------------------------------
    def test_transfer_and_cheque_details(self):
        Wizard = self.env['hotel.reservation.payment.wizard']
        for offset, (mode, number_field, payment_field) in enumerate((
                ('transfer', 'transfer_reference', 'hotel_transfer_number'),
                ('cheque', 'cheque_reference', 'hotel_cheque_number'))):
            shift = timedelta(days=20 * (offset + 1))
            resa = self._resa(checkin=self.ci + shift, checkout=self.co + shift)
            wizard = Wizard.create({
                'reservation_id': resa.id, 'payment_mode': mode, 'amount': 1000,
                'encaisse_kind': 'payment'})
            with self.assertRaises(UserError):  # banque et numéro obligatoires
                wizard.action_confirm()
            wizard.write({'bank_name': ' CPA ', number_field: 'N-4521'})
            wizard.action_confirm()
            payment = resa.payment_ids
            self.assertEqual(payment.hotel_payment_mode, mode)
            self.assertEqual(payment.hotel_bank_name, 'CPA')
            self.assertEqual(payment[payment_field], 'N-4521')
            self.assertIn('N-4521', payment.memo)

    # --- Lits proposés = lits libres sur toute la période ---------------------
    def test_only_free_beds_proposed(self):
        bed1, bed2 = self.dorm.bed_ids[:2]
        other = self._resa(booking_type='bed', checkin=self.ci, checkout=self.co,
                           line_ids=[(0, 0, {'bed_id': bed1.id})])
        other.action_confirm()
        Resa = self.env['hotel.reservation']
        # Chevauchement partiel (une nuit en commun) : lit non proposé
        new = Resa.new({'checkin': self.ci - timedelta(days=3),
                        'checkout': self.ci + timedelta(days=1), 'booking_type': 'bed',
                        'guest_count': 2})
        self.assertNotIn(bed1, new.proposed_bed_ids._origin)
        self.assertIn(bed2, new.proposed_bed_ids._origin)
        # Période qui englobe l'autre réservation : non proposé non plus
        new = Resa.new({'checkin': self.ci - timedelta(days=1),
                        'checkout': self.co + timedelta(days=1), 'booking_type': 'bed',
                        'guest_count': 2})
        self.assertNotIn(bed1, new.proposed_bed_ids._origin)
        # Arrivée le jour du départ de l'autre client : le lit est libre
        new = Resa.new({'checkin': self.co, 'checkout': self.co + timedelta(days=2),
                        'booking_type': 'bed', 'guest_count': 3})
        self.assertIn(bed1, new.proposed_bed_ids._origin)
        # Lit choisi puis dates changées vers une période où il est pris :
        # il est retiré de la réservation avec un avertissement
        form = Form(Resa)
        form.partner_id = self.partner
        form.booking_type = 'bed'
        form.checkin = self.co + timedelta(days=1)
        form.checkout = self.co + timedelta(days=3)
        with form.line_ids.new() as line:
            line.bed_id = bed1
        self.assertEqual(len(form.line_ids), 1)
        form.checkin = self.ci
        self.assertEqual(len(form.line_ids), 0)

    # --- Remise client supprimée ---------------------------------------------
    def test_no_partner_discount(self):
        self.assertNotIn('hotel_discount', self.env['res.partner']._fields)
        view = self.env.ref('hotel_management.view_partner_hotel_rates_list').arch
        self.assertNotIn('hotel_discount', view)

    # --- Déjà pris (même en brouillon) = non proposé -------------------------
    def test_draft_blocks_proposals(self):
        Resa = self.env['hotel.reservation']
        (self.env['hotel.room'].search([]) - self.room - self.dorm).write(
            {'technical_state': 'out_of_service'})
        new = Resa.new({'checkin': self.ci, 'checkout': self.co, 'booking_type': 'room'})
        self.assertIn(self.room, new.proposed_room_ids._origin)
        self._resa()  # brouillon sur RR-1
        new = Resa.new({'checkin': self.ci, 'checkout': self.co, 'booking_type': 'room'})
        self.assertNotIn(self.room, new.proposed_room_ids._origin)

        bed = self.dorm.bed_ids[0]
        self._resa(booking_type='bed', line_ids=[(0, 0, {'bed_id': bed.id})])  # brouillon
        new = Resa.new({'checkin': self.ci, 'checkout': self.co, 'booking_type': 'bed',
                        'guest_count': len(self.dorm.bed_ids) - 1})
        proposed = new.proposed_bed_ids._origin
        self.assertNotIn(bed, proposed)
        # Dortoir entamé avec autant de lits libres que de personnes : ses lits restants
        self.assertEqual(proposed[:len(self.dorm.bed_ids) - 1], self.dorm.bed_ids[1:])

    def test_taken_not_proposed_without_checkout(self):
        """Nouvelle réservation, départ pas encore saisi (seule l'arrivée est
        remplie par défaut) : ce qui est pris n'est quand même pas proposé."""
        Resa = self.env['hotel.reservation']
        self._resa().action_confirm()
        bed = self.dorm.bed_ids[0]
        self._resa(booking_type='bed', line_ids=[(0, 0, {'bed_id': bed.id})])
        for vals in ({'checkin': self.ci}, {'checkin': self.ci, 'checkout': self.ci}):
            form = Form(Resa)
            form.partner_id = self.partner
            form.checkin = vals['checkin']
            if 'checkout' in vals:
                form.checkout = vals['checkout']
            self.assertNotIn(self.room.id, form.proposed_room_ids.ids)
            form.booking_type = 'bed'
            self.assertNotIn(bed.id, form.proposed_bed_ids.ids)
            self.assertTrue(form.proposed_bed_ids.ids)
        # Aucune date : à partir d'aujourd'hui (une nuit)
        new = Resa.new({'booking_type': 'room', 'checkin': False})
        self.assertEqual(new._proposal_period()[0], fields.Date.context_today(new))

    # --- « Envoyer mail » sur plusieurs réservations enregistrées ---------------
    def _three_reservations(self):
        no_mail = self.env['res.partner'].create({
            'name': 'Second client', 'hotel_last_name': 'Benali', 'hotel_id_number': 'ID-42',
            'hotel_first_name': 'Second', 'hotel_birthdate': '1985-01-01', 'phone': '0550000007',
            'street': '2 rue Test', 'hotel_id_type': 'cni'})
        resas = self.env['hotel.reservation']
        for partner, state in ((self.partner, 'checkin'), (no_mail, 'checkin'),
                               (self.partner, 'confirmed')):
            room = self.env['hotel.room'].create({
                'name': 'RR-M%s' % len(resas), 'capacity': 2})
            resa = self._resa(partner_id=partner.id,
                              line_ids=[(0, 0, {'room_id': room.id, 'price_unit': 1000})])
            resa.action_confirm()
            if state == 'checkin':
                resa.action_checkin()
            resas |= resa
        return resas

    def test_mail_wizard_selection(self):
        resas = self._three_reservations()
        Wizard = self.env['hotel.reservation.mail.wizard']
        wizard = Wizard.with_context(
            active_model='hotel.reservation', active_ids=resas.ids).create({
                'email_to': 'police@example.com'})
        # Seules les réservations « Enregistrée » sont reprises
        self.assertEqual(wizard.reservation_ids, resas[:2])
        self.assertIn(resas[2].name, wizard.skipped_info)
        self.assertIn(resas[0].name, wizard.body)
        self.assertIn(resas[1].name, wizard.body)
        self.assertIn('ID-42', wizard.body)
        self.assertIn('(2)', wizard.subject)
        mails_before = self.env['mail.mail'].search_count([])
        wizard.action_send()
        self.assertEqual(self.env['mail.mail'].search_count([]), mails_before + 1)
        for resa in resas[:2]:
            self.assertIn('police@example.com', resa.message_ids[0].body)
        # Aucune réservation enregistrée dans la sélection : refus clair
        with self.assertRaises(UserError):
            Wizard.with_context(active_model='hotel.reservation',
                                active_ids=resas[2].ids).create({'email_to': 'x@example.com'})
        # Depuis la fiche : une réservation, quel que soit son état
        single = Wizard.with_context(default_reservation_id=resas[2].id,
                                     active_model='hotel.reservation',
                                     active_id=resas[2].id).create({})
        self.assertEqual(single.reservation_ids, resas[2])
        self.assertEqual(single.email_to, self.partner.email)
        view = self.env.ref('hotel_management.view_hotel_reservation_tree').arch
        self.assertIn('Envoyer mail', view)
        self.assertNotIn('action_send_confirmation_selection', view)


@tagged('post_install', '-at_install')
class TestReceptionMailUi(HttpCase):

    def test_list_send_mail_button(self):
        """Liste des réservations : cocher 2 réservations -> « Envoyer mail »."""
        self.env.ref('base.user_admin').password = 'admin'
        self.browser_js(
            '/odoo/action-hotel_management.action_hotel_reservation',
            """
            const boxes = [...document.querySelectorAll('.o_data_row .o_list_record_selector input')];
            boxes.slice(0, 2).forEach((b) => b.click());
            setTimeout(() => {
                const btn = [...document.querySelectorAll('.o_control_panel button, .o_list_view button')]
                    .find((b) => b.textContent.trim() === 'Envoyer mail');
                if (!btn) {
                    console.error('Bouton Envoyer mail absent');
                    return;
                }
                btn.click();
                const t = setInterval(() => {
                    const modal = document.querySelector('.modal');
                    if (modal && (modal.querySelector(".o_field_widget[name='email_to']")
                                  || modal.textContent.includes('Enregistrée'))) {
                        clearInterval(t);
                        console.log('test successful');
                    }
                }, 300);
            }, 1000);
            """,
            ready="document.querySelectorAll('.o_data_row').length >= 2",
            login='admin', timeout=90)
