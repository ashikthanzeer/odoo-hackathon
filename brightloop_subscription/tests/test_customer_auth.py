# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, AccessError


class TestCustomerAuth(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ResUsers = cls.env['res.users']
        cls.ResPartner = cls.env['res.partner']
        cls.group_staff = cls.env.ref('brightloop_subscription.group_subscription_user')
        cls.group_manager = cls.env.ref('brightloop_subscription.group_subscription_manager')

        # Create an administrative user with settings access to manage users
        cls.admin_user = cls.ResUsers.create({
            'name': 'Subscription Admin',
            'login': 'sub_admin@brightloop.test',
            'email': 'sub_admin@brightloop.test',
            'password': 'AdminSecurePassword@123',
            'group_ids': [(6, 0, [
                cls.group_manager.id,
                cls.env.ref('base.group_user').id,
                cls.env.ref('base.group_system').id,
            ])]
        })

        # Create a standard internal staff user
        cls.staff_user = cls.ResUsers.with_user(cls.admin_user).create({
            'name': 'Staff User',
            'login': 'staff_user@brightloop.test',
            'email': 'staff_user@brightloop.test',
            'password': 'StaffSecurePassword#456',
            'group_ids': [(6, 0, [cls.group_staff.id, cls.env.ref('base.group_user').id])]
        })

    def test_01_password_complexity_length(self):
        """Verify password <= 8 characters is rejected."""
        with self.assertRaises(ValidationError):
            self.ResUsers.with_user(self.admin_user).create({
                'name': 'Short Pass User',
                'login': 'short_pass@brightloop.test',
                'email': 'short_pass@brightloop.test',
                'password': 'Ab1@efg'  # 7 chars
            })

    def test_02_password_complexity_missing_uppercase(self):
        """Verify password without uppercase is rejected."""
        with self.assertRaises(ValidationError):
            self.ResUsers.with_user(self.admin_user).create({
                'name': 'No Upper User',
                'login': 'no_upper@brightloop.test',
                'email': 'no_upper@brightloop.test',
                'password': 'validpassword#123'
            })

    def test_03_password_complexity_missing_lowercase(self):
        """Verify password without lowercase is rejected."""
        with self.assertRaises(ValidationError):
            self.ResUsers.with_user(self.admin_user).create({
                'name': 'No Lower User',
                'login': 'no_lower@brightloop.test',
                'email': 'no_lower@brightloop.test',
                'password': 'VALIDPASSWORD#123'
            })

    def test_04_password_complexity_missing_special_char(self):
        """Verify password without special character is rejected."""
        with self.assertRaises(ValidationError):
            self.ResUsers.with_user(self.admin_user).create({
                'name': 'No Special User',
                'login': 'no_special@brightloop.test',
                'email': 'no_special@brightloop.test',
                'password': 'ValidPassword123'
            })

    def test_05_valid_password_creation_succeeds(self):
        """Verify password meeting all criteria succeeds (>8 chars, uppercase, lowercase, special)."""
        valid_user = self.ResUsers.with_user(self.admin_user).create({
            'name': 'Valid User',
            'login': 'valid_user@brightloop.test',
            'email': 'valid_user@brightloop.test',
            'password': 'ValidStrongPassword!999'
        })
        self.assertTrue(valid_user.id)

    def test_06_unique_email_enforcement(self):
        """Verify duplicate registration with the same email is blocked."""
        self.ResUsers.with_user(self.admin_user).create({
            'name': 'User One',
            'login': 'unique_user@brightloop.test',
            'email': 'unique_user@brightloop.test',
            'password': 'UserOneStrongPassword#1'
        })
        with self.assertRaises(ValidationError):
            self.ResUsers.with_user(self.admin_user).create({
                'name': 'User Two Duplicate',
                'login': 'unique_user_different_login@brightloop.test',
                'email': 'unique_user@brightloop.test',
                'password': 'UserTwoStrongPassword#2'
            })

    def test_07_only_admin_can_add_staff(self):
        """Verify internal staff cannot provision or grant staff permissions to users."""
        with self.assertRaises(AccessError):
            self.ResUsers.with_user(self.staff_user).create({
                'name': 'Unauthorized New Staff',
                'login': 'unauth_staff@brightloop.test',
                'email': 'unauth_staff@brightloop.test',
                'password': 'ValidStaffPass$789',
                'group_ids': [(6, 0, [self.group_staff.id])]
            })
