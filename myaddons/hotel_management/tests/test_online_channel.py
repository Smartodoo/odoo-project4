from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOnlineChannel(TransactionCase):
    """Réservation faite sur le site -> message dans le canal « Réservations
    en ligne » (admin membre) ; autres sources -> notification habituelle."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env.ref('hotel_management.channel_online_reservations')
        rtype = cls.env['hotel.room.type'].create({'name': 'OC', 'room_price': 1500})
        cls.room = cls.env['hotel.room'].create({
            'name': 'OC-1', 'capacity': 2})
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

    def test_new_users_auto_member(self):
        """Utilisateur créé (ou modifié) avec l'accès Réception ou Responsable
        -> membre du canal ; simple employé -> non."""
        Users = self.env['res.users'].with_context(no_reset_password=True)
        members = lambda: self.channel.channel_member_ids.partner_id
        reception = Users.create({
            'name': 'OC Réception', 'login': 'oc_reception@example.com',
            'group_ids': [Command.link(self.env.ref('hotel_management.group_hotel_user').id)]})
        manager = Users.create({
            'name': 'OC Responsable', 'login': 'oc_manager@example.com',
            'group_ids': [Command.link(self.env.ref('hotel_management.group_hotel_manager').id)]})
        employee = Users.create({
            'name': 'OC Employé', 'login': 'oc_employee@example.com',
            'group_ids': [Command.link(self.env.ref('base.group_user').id)]})
        self.assertIn(reception.partner_id, members())
        self.assertIn(manager.partner_id, members())
        self.assertNotIn(employee.partner_id, members())
        # Accès Réception donné plus tard -> ajouté aussi
        employee.write({'group_ids': [Command.link(self.env.ref('hotel_management.group_hotel_user').id)]})
        self.assertIn(employee.partner_id, members())

    def test_users_removed_when_access_lost(self):
        """Accès Réception / Responsable retiré -> retiré du canal (sauf s'il
        garde un accès qui y donne droit)."""
        Users = self.env['res.users'].with_context(no_reset_password=True)
        g_user = self.env.ref('hotel_management.group_hotel_user')
        g_manager = self.env.ref('hotel_management.group_hotel_manager')
        g_employee = self.env.ref('base.group_user')
        members = lambda: self.channel.channel_member_ids.partner_id
        # 1) depuis la fiche utilisateur
        reception = Users.create({'name': 'OC R2', 'login': 'oc_r2@example.com',
                                  'group_ids': [Command.link(g_user.id)]})
        self.assertIn(reception.partner_id, members())
        reception.write({'group_ids': [Command.unlink(g_user.id), Command.unlink(g_manager.id)]})
        self.assertNotIn(reception.partner_id, members())
        # 2) Responsable rétrogradé en Réception -> reste membre
        manager = Users.create({'name': 'OC M2', 'login': 'oc_m2@example.com',
                                'group_ids': [Command.link(g_manager.id)]})
        manager.write({'group_ids': [Command.unlink(g_manager.id), Command.link(g_user.id)]})
        self.assertIn(manager.partner_id, members())
        # 3) depuis la fiche du groupe
        g_user.write({'user_ids': [Command.unlink(manager.id)]})
        self.assertNotIn(manager.partner_id, members())
        # 4) l'admin reste toujours membre
        self.assertIn(self.env.ref('base.partner_admin'), members())
        # 5) un employé sans accès hôtel modifié : rien ne casse
        employee = Users.create({'name': 'OC E2', 'login': 'oc_e2@example.com',
                                 'group_ids': [Command.link(g_employee.id)]})
        employee.write({'group_ids': [Command.link(g_employee.id)]})
        self.assertNotIn(employee.partner_id, members())
