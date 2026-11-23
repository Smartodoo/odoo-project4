from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestStaffUser(TransactionCase):
    """Agent de l'auberge = employé + utilisateur créés automatiquement."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))
        cls.Staff = cls.env['hotel.staff'].with_context(no_reset_password=True)

    def test_create_makes_user_and_employee(self):
        agent = self.Staff.create({'name': 'Amina Saïdi', 'role': 'reception',
                                   'phone': '0550123456'})
        user, employee = agent.user_id, agent.employee_id
        self.assertTrue(user and employee)
        self.assertEqual(employee.user_id, user)
        self.assertEqual(user.login, 'amina.saidi')
        self.assertEqual(employee.mobile_phone, '0550123456')
        self.assertTrue(user.has_group('base.group_user'))
        self.assertTrue(user.has_group('hotel_management.group_hotel_user'))
        self.assertFalse(user.has_group('hotel_management.group_hotel_manager'))
        # Même nom : identifiant rendu unique
        other = self.Staff.create({'name': 'Amina Saidi', 'role': 'housekeeping'})
        self.assertEqual(other.user_id.login, 'amina.saidi2')
        self.assertTrue(other.user_id.has_group('hotel_management.group_hotel_housekeeping'))
        self.assertFalse(other.user_id.has_group('hotel_management.group_hotel_user'))

    def test_email_is_login_and_sync(self):
        agent = self.Staff.create({'name': 'Karim', 'role': 'housekeeping',
                                   'email': 'karim.agent@example.com'})
        self.assertEqual(agent.user_id.login, 'karim.agent@example.com')
        self.assertEqual(agent.employee_id.work_email, 'karim.agent@example.com')
        # Fonction -> droits ; nom -> employé et utilisateur ; archivage
        agent.write({'role': 'manager', 'name': 'Karim B.'})
        self.assertTrue(agent.user_id.has_group('hotel_management.group_hotel_manager'))
        self.assertEqual(agent.employee_id.name, 'Karim B.')
        self.assertEqual(agent.user_id.name, 'Karim B.')
        agent.role = 'other'
        self.assertFalse(agent.user_id.has_group('hotel_management.group_hotel_housekeeping'))
        self.assertTrue(agent.user_id.has_group('base.group_user'))
        user, employee = agent.user_id, agent.employee_id
        agent.active = False
        self.assertFalse(user.active)
        self.assertFalse(employee.active)

    def test_existing_employee_reused(self):
        employee = self.env['hr.employee'].create({'name': 'Employé existant'})
        agent = self.Staff.create({'name': 'Employé existant', 'employee_id': employee.id,
                                   'role': 'maintenance'})
        self.assertEqual(agent.employee_id, employee)
        self.assertEqual(employee.user_id, agent.user_id)
        self.assertEqual(self.env['hr.employee'].search_count([('name', '=', 'Employé existant')]), 1)

    def test_reception_cannot_create_agents(self):
        reception = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Réception test', 'login': 'reception.test.staff',
            'group_ids': [(6, 0, [self.env.ref('hotel_management.group_hotel_user').id])]})
        with self.assertRaises(UserError):
            self.env['hotel.staff'].with_user(reception).create({'name': 'Intrus', 'role': 'manager'})
