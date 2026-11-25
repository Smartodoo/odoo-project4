from datetime import date

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestWebsiteSearchOrder(HttpCase):
    """Recherche du site : type obligatoire et ordre des résultats."""

    CI, CO = '2092-03-10', '2092-03-12'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Room = cls.env['hotel.room']
        btype = cls.env['hotel.room.type'].create({'name': 'ZS dortoir'})
        rtype = cls.env['hotel.room.type'].create({'name': 'ZS privée'})

        def room(name, cap, mode, rtype_):
            return Room.create({
                'name': name, 'capacity': cap,
                'website_published': True})

        # par lit : P1 = 1 lit libre, P2 = 2 lits libres (partagées) ; E2 / E3 vides
        cls.p1 = room('ZS-P1', 3, 'bed', btype)
        cls.p2 = room('ZS-P2', 3, 'bed', btype)
        cls.e2 = room('ZS-E2', 2, 'bed', btype)
        cls.e3 = room('ZS-E3', 3, 'bed', btype)
        # par chambre
        cls.r1 = room('ZS-R1', 1, 'room', rtype)
        cls.r2 = room('ZS-R2', 2, 'room', rtype)
        cls.r3 = room('ZS-R3', 3, 'room', rtype)
        partner = cls.env['res.partner'].create({'hotel_last_name': 'Test', 'hotel_first_name': 'Client', 'phone': '0550000009', 'street': '1 rue Test', 'hotel_id_type': 'cni', 'hotel_id_number': 'ID-T', 'name': 'ZS client', 'hotel_birthdate': '1990-01-01'})
        beds = cls.p1.bed_ids[:2] | cls.p2.bed_ids[:1]
        resa = cls.env['hotel.reservation'].create({
            'partner_id': partner.id, 'checkin': date(2092, 3, 10), 'checkout': date(2092, 3, 12),
            'booking_type': 'bed', 'children': len(beds) - 1,
            'line_ids': [(0, 0, {'bed_id': b.id}) for b in beds]})
        resa.action_confirm()

    def _order(self, booking_type, guests, names):
        html = self.url_open('/hotel/rooms?checkin=%s&checkout=%s&guests=%s&booking_type=%s' % (
            self.CI, self.CO, guests, booking_type)).text
        available = html.split('Non disponibles sur cette période')[0]
        found = [(available.find('Chambre %s<' % n), n) for n in names]
        return [n for pos, n in sorted(found) if pos >= 0], html

    def test_bed_order(self):
        # chambres partagées seulement (les chambres vides ne sont pas
        # proposées tant qu'une chambre partagée peut loger le groupe)
        order, _html = self._order('bed', 1, ['ZS-P1', 'ZS-P2', 'ZS-E2', 'ZS-E3'])
        self.assertEqual(order, ['ZS-P1', 'ZS-P2'])
        # 2 voyageurs : P1 (1 lit libre) ne convient plus
        order, _html = self._order('bed', 2, ['ZS-P1', 'ZS-P2', 'ZS-E2', 'ZS-E3'])
        self.assertEqual(order, ['ZS-P2'])
        # 3 voyageurs : aucune chambre partagée assez grande -> chambres vides
        order, _html = self._order('bed', 3, ['ZS-P1', 'ZS-P2', 'ZS-E2', 'ZS-E3'])
        self.assertEqual(order, ['ZS-E3'])

    def test_room_order(self):
        order, _html = self._order('room', 2, ['ZS-R1', 'ZS-R2', 'ZS-R3'])
        self.assertEqual(order, ['ZS-R2', 'ZS-R3'])
        order, _html = self._order('room', 1, ['ZS-R1', 'ZS-R2', 'ZS-R3'])
        self.assertEqual(order, ['ZS-R1', 'ZS-R2', 'ZS-R3'])

    def test_type_required(self):
        html = self.url_open('/hotel/rooms?checkin=%s&checkout=%s&guests=1' % (self.CI, self.CO)).text
        self.assertIn('Choisissez le type de location', html)
        self.assertNotIn('>Tout<', html)
        self.assertNotIn('Chambre ZS-P1<', html.split('Nos chambres')[0])
