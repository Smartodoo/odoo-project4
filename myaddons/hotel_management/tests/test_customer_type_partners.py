from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCustomerTypePartners(TransactionCase):

    def test_type_lists_its_partners(self):
        ctype = self.env['hotel.customer.type'].create({'name': 'Test fidèle'})
        p1 = self.env['res.partner'].create({'name': 'Client A', 'hotel_customer_type_id': ctype.id})
        p2 = self.env['res.partner'].create({'name': 'Client B', 'hotel_customer_type_id': ctype.id})
        self.env['res.partner'].create({'name': 'Client C'})
        self.assertEqual(ctype.partner_ids, p1 | p2)
        self.assertEqual(ctype.partner_count, 2)
        action = ctype.action_view_partners()
        self.assertEqual(self.env['res.partner'].search(action['domain']), p1 | p2)
        self.assertEqual(action['context']['default_hotel_customer_type_id'], ctype.id)

    def test_contacts_search_filters(self):
        env = self.env(user=self.env.ref('base.user_admin'))
        arch = env['res.partner'].get_view(
            self.env.ref('base.view_res_partner_filter').id, 'search')['arch']
        self.assertIn('group_hotel_customer_type', arch)
        self.assertIn('hotel_customer_type_id', arch)
        form = env['hotel.customer.type'].get_view(view_type='form')['arch']
        self.assertIn('partner_ids', form)
