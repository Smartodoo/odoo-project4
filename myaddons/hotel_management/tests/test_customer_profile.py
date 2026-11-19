from datetime import timedelta

from odoo import fields
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCustomerProfile(TransactionCase):
    """Type de client + préférences : partagés entre fiche client et réservation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))
        cls.vip = cls.env.ref('hotel_management.customer_type_vip')
        cls.blacklist = cls.env.ref('hotel_management.customer_type_blacklist')
        cls.partner = cls.env['res.partner'].create({
            'name': 'Client profil', 'hotel_birthdate': '1990-01-01',
            'hotel_customer_type_id': cls.vip.id,
            'hotel_preferences': 'Chambre calme, étage élevé'})
        rtype = cls.env['hotel.room.type'].create({'name': 'Type profil', 'list_price': 3000})
        cls.room = cls.env['hotel.room'].create({
            'name': 'CP-1', 'room_type_id': rtype.id, 'capacity': 2,
            'room_price': 3000, 'bed_price': 1000, 'rental_mode': 'room'})
        cls.ci = fields.Date.today() + timedelta(days=950)

    def test_default_types(self):
        names = self.env['hotel.customer.type'].search([]).mapped('name')
        for name in ('Client fidèle', 'Client VIP', 'Liste noire'):
            self.assertIn(name, names)

    def test_reservation_prefilled_and_writes_back(self):
        # Choix du client sur une nouvelle réservation : profil pré-rempli
        f = Form(self.env['hotel.reservation'])
        f.partner_id = self.partner
        self.assertEqual(f.partner_customer_type_id, self.vip)
        self.assertEqual(f.partner_preferences, 'Chambre calme, étage élevé')
        # Modification depuis le formulaire d'une réservation : la fiche client suit
        resa = self.env['hotel.reservation'].create({
            'partner_id': self.partner.id, 'checkin': self.ci,
            'checkout': self.ci + timedelta(days=1), 'booking_type': 'room',
            'line_ids': [(0, 0, {'room_id': self.room.id})]})
        with Form(resa) as f:
            f.partner_customer_type_id = self.blacklist
            f.partner_preferences = 'Pas de petit-déjeuner'
        self.assertEqual(self.partner.hotel_customer_type_id, self.blacklist)
        self.assertEqual(self.partner.hotel_preferences, 'Pas de petit-déjeuner')

    def test_partner_change_reflected_on_reservation(self):
        resa = self.env['hotel.reservation'].create({
            'partner_id': self.partner.id, 'checkin': self.ci,
            'checkout': self.ci + timedelta(days=1), 'booking_type': 'room',
            'line_ids': [(0, 0, {'room_id': self.room.id})]})
        self.partner.hotel_preferences = 'Lit bébé'
        self.assertEqual(resa.partner_preferences, 'Lit bébé')
        resa.partner_customer_type_id = False
        self.assertFalse(self.partner.hotel_customer_type_id)

    def test_blacklist_alert(self):
        self.assertTrue(self.blacklist.is_blacklist)
        self.assertFalse(self.vip.is_blacklist)
        self.partner.hotel_customer_type_id = self.blacklist
        self.assertTrue(self.partner.hotel_is_blacklisted)
        resa = self.env['hotel.reservation'].new({'partner_id': self.partner.id})
        self.assertTrue(resa.partner_is_blacklisted)
        warning = resa._onchange_partner_id_hotel()
        self.assertTrue(warning and warning.get('warning'))
        self.assertIn('Liste noire', warning['warning']['message'])
        # Client VIP : pas d'alerte
        self.partner.hotel_customer_type_id = self.vip
        resa = self.env['hotel.reservation'].new({'partner_id': self.partner.id})
        self.assertFalse(resa.partner_is_blacklisted)
        self.assertFalse(resa._onchange_partner_id_hotel())
