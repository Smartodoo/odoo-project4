from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOnlineChannel(TransactionCase):
    """Réservation faite sur le site -> message dans le canal « Réservations
    en ligne » (admin membre) ; autres sources -> notification habituelle."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env.ref('hotel_management.channel_online_reservations')
        rtype = cls.env['hotel.room.type'].create({'name': 'OC', 'list_price': 1500})
        cls.room = cls.env['hotel.room'].create({
            'name': 'OC-1', 'room_type_id': rtype.id, 'capacity': 2,
            'room_price': 1500, 'rental_mode': 'room'})
        cls.partner = cls.env['res.partner'].create({
            'hotel_last_name': 'Canal', 'hotel_first_name': 'Client',
            'email': 'canal@example.com', 'phone': '0550123456'})
        cls.ci = fields.Date.today() + timedelta(days=1500)

    def _resa(self, source, days=0):
        return self.env['hotel.reservation'].create({
            'partner_id': self.partner.id, 'source': source,
            'checkin': self.ci + timedelta(days=days),
            'checkout': self.ci + timedelta(days=days + 2),
            'guest_count': 1, 'line_ids': [(0, 0, {'room_id': self.room.id})]})

    def test_admin_is_member(self):
        self.assertEqual(self.channel.name, 'Réservations en ligne')
        self.assertIn(self.env.ref('base.partner_admin'),
                      self.channel.channel_member_ids.partner_id)

    def test_website_reservation_posted_in_channel(self):
        before = len(self.channel.message_ids)
        resa = self._resa('website')
        msgs = self.channel.message_ids
        self.assertEqual(len(msgs), before + 1)
        body = str(msgs[0].body)
        self.assertIn(resa.name, body)
        self.assertIn('Canal Client', body)
        self.assertIn('0550123456', body)
        self.assertIn('OC-1', body)
        self.assertIn('/odoo/action-hotel_management.action_hotel_reservation_online/%s' % resa.id, body)

    def test_other_source_not_in_channel(self):
        before = len(self.channel.message_ids)
        self._resa('direct', days=10)
        self.assertEqual(len(self.channel.message_ids), before)
