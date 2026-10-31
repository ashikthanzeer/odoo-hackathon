# -*- coding: utf-8 -*-
from datetime import date
from dateutil.relativedelta import relativedelta
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError, AccessError


class TestDiscountRules(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.DiscountRuleModel = cls.env['subscription.discount.rule']
        cls.PlanModel = cls.env['subscription.plan']
        cls.SubscriptionModel = cls.env['subscription.subscription']
        cls.ProductTemplate = cls.env['product.template']
        cls.PartnerModel = cls.env['res.partner']
        cls.UserModel = cls.env['res.users']

        # Setup Groups
        cls.group_manager = cls.env.ref('brightloop_subscription.group_subscription_manager')
        cls.group_user = cls.env.ref('brightloop_subscription.group_subscription_user')

        # Setup Admin User
        cls.admin_user = cls.UserModel.create({
            'name': 'Brightloop Subscription Admin',
            'login': 'sub_admin@brightloop.test',
            'email': 'sub_admin@brightloop.test',
            'groups_id': [(6, 0, [cls.group_manager.id, cls.env.ref('base.group_user').id])],
        })

        # Setup Internal Staff User
        cls.staff_user = cls.UserModel.create({
            'name': 'Brightloop Sales Staff',
            'login': 'sub_staff@brightloop.test',
            'email': 'sub_staff@brightloop.test',
            'groups_id': [(6, 0, [cls.group_user.id, cls.env.ref('base.group_user').id])],
        })

        # Setup Partner
        cls.customer = cls.PartnerModel.create({
            'name': 'Brightloop Discount Test Customer',
            'email': 'discount_test@brightloop.test',
            'is_subscription_customer': True,
        })

        # Setup Monthly Plan
        cls.monthly_plan = cls.PlanModel.create({
            'name': 'Monthly Cloud Plan',
            'code': 'MCP-DISC',
            'billing_cycle_unit': 'monthly',
            'billing_interval': 1,
            'min_quantity': 1.0,
        })

        # Setup Subscription Products
        cls.product_tmpl_a = cls.ProductTemplate.create({
            'name': 'Cloud Collaboration Suite',
            'detailed_type': 'service',
            'list_price': 100.0,
            'is_subscription': True,
        })
        cls.product_a = cls.product_tmpl_a.product_variant_id

        cls.product_tmpl_b = cls.ProductTemplate.create({
            'name': 'Add-on Dedicated IP',
            'detailed_type': 'service',
            'list_price': 50.0,
            'is_subscription': True,
        })
        cls.product_b = cls.product_tmpl_b.product_variant_id

    def test_01_admin_only_discount_rule_governance(self):
        """Verify only administrators can create, edit, or delete discount rules; staff cannot."""
        # Admin creates rule successfully
        admin_rule = self.DiscountRuleModel.with_user(self.admin_user).create({
            'name': 'Admin Promo 10%',
            'discount_type': 'percentage',
            'discount_value': 10.0,
            'scope': 'whole_subscription',
        })
        self.assertTrue(admin_rule.id)

        # Internal staff attempts to create rule -> AccessError
        with self.assertRaises(AccessError):
            self.DiscountRuleModel.with_user(self.staff_user).create({
                'name': 'Staff Unauthorized Promo',
                'discount_type': 'percentage',
                'discount_value': 20.0,
                'scope': 'whole_subscription',
            })

        # Internal staff attempts to modify rule configuration -> AccessError
        with self.assertRaises(AccessError):
            admin_rule.with_user(self.staff_user).write({
                'discount_value': 15.0,
            })

        # Internal staff attempts to delete rule -> AccessError
        with self.assertRaises(AccessError):
            admin_rule.with_user(self.staff_user).unlink()

        # Admin can delete successfully
        admin_rule.with_user(self.admin_user).unlink()

    def test_02_percentage_and_fixed_discount_calculations(self):
        """Verify percentage and fixed discount calculations for whole subscription and specific products."""
        # 1. Percentage discount on whole subscription (10%)
        rule_pct = self.DiscountRuleModel.with_user(self.admin_user).create({
            'name': '10% Whole Subscription Discount',
            'discount_type': 'percentage',
            'discount_value': 10.0,
            'scope': 'whole_subscription',
        })

        sub1 = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'discount_rule_id': rule_pct.id,
            'line_ids': [(0, 0, {
                'product_id': self.product_a.id,
                'quantity': 20.0,
                'price_unit': 100.0,  # untaxed = 2000.00
            })]
        })
        self.assertEqual(sub1.amount_untaxed, 2000.0)
        self.assertEqual(sub1.discount_amount, 200.0)
        self.assertEqual(sub1.amount_net, 1800.0)

        # 2. Fixed discount on specific product ($50 off Product A only)
        rule_fixed = self.DiscountRuleModel.with_user(self.admin_user).create({
            'name': '$50 Off Product A',
            'discount_type': 'fixed',
            'discount_value': 50.0,
            'scope': 'specific_products',
            'product_ids': [(6, 0, [self.product_a.id])],
        })

        sub2 = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'discount_rule_id': rule_fixed.id,
            'line_ids': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'quantity': 2.0,
                    'price_unit': 100.0,  # 200.00
                }),
                (0, 0, {
                    'product_id': self.product_b.id,
                    'quantity': 1.0,
                    'price_unit': 50.0,   # 50.00
                }),
            ]
        })
        # Untaxed = 250.00. Product A line is 200.00. Fixed discount = 50.00.
        self.assertEqual(sub2.amount_untaxed, 250.0)
        self.assertEqual(sub2.discount_amount, 50.0)
        self.assertEqual(sub2.amount_net, 200.0)

    def test_03_min_quantity_and_amount_thresholds(self):
        """Verify min_quantity and min_amount eligibility constraints."""
        rule_threshold = self.DiscountRuleModel.with_user(self.admin_user).create({
            'name': 'Volume 10+ Seats & $1000+ Spend',
            'discount_type': 'percentage',
            'discount_value': 15.0,
            'scope': 'whole_subscription',
            'min_quantity': 10.0,
            'min_amount': 1000.0,
        })

        # Order below thresholds (8 seats, $800)
        sub_below = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'discount_rule_id': rule_threshold.id,
            'line_ids': [(0, 0, {
                'product_id': self.product_a.id,
                'quantity': 8.0,
                'price_unit': 100.0,
            })]
        })
        self.assertFalse(rule_threshold.is_eligible(sub_below))
        self.assertEqual(sub_below.discount_amount, 0.0)
        self.assertEqual(sub_below.amount_net, 800.0)

        # Order meets thresholds (12 seats, $1200)
        sub_above = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'discount_rule_id': rule_threshold.id,
            'line_ids': [(0, 0, {
                'product_id': self.product_a.id,
                'quantity': 12.0,
                'price_unit': 100.0,
            })]
        })
        self.assertTrue(rule_threshold.is_eligible(sub_above))
        self.assertEqual(sub_above.discount_amount, 180.0)
        self.assertEqual(sub_above.amount_net, 1020.0)

    def test_04_automatic_invoice_generation_and_counter_increment(self):
        """Verify generating invoice adds discount line item and increments usage counter."""
        rule = self.DiscountRuleModel.with_user(self.admin_user).create({
            'name': 'Client Onboarding 10%',
            'code': 'ONBOARD10',
            'discount_type': 'percentage',
            'discount_value': 10.0,
            'scope': 'whole_subscription',
            'max_usage_limit': 5,
        })

        today = date(2026, 6, 1)
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'discount_rule_id': rule.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product_a.id,
                'quantity': 5.0,
                'price_unit': 100.0,  # 500.00
            })]
        })
        sub.action_confirm()

        self.assertEqual(rule.current_usage_count, 0)

        # Generate Invoice
        invoice = sub.action_generate_invoice(target_date=today)
        self.assertTrue(invoice)
        self.assertEqual(len(invoice.invoice_line_ids), 2)  # 1 product line + 1 discount line

        product_line = invoice.invoice_line_ids.filtered(lambda l: l.product_id == self.product_a)
        discount_line = invoice.invoice_line_ids.filtered(lambda l: not l.product_id or l.price_unit < 0)

        self.assertEqual(product_line.price_unit, 100.0)
        self.assertEqual(product_line.quantity, 5.0)
        self.assertEqual(discount_line.price_unit, -50.0)
        self.assertIn('ONBOARD10', discount_line.name)

        # Usage counter should increment to 1
        self.assertEqual(rule.current_usage_count, 1)

    def test_05_automatic_cessation_on_cap_exhaustion_and_expiry(self):
        """Verify automatic cessation of discount when max_usage_limit is reached or end_date passes."""
        # 1. Cap Exhaustion Test (max_usage_limit = 1)
        rule_capped = self.DiscountRuleModel.with_user(self.admin_user).create({
            'name': 'Single-Use Welcome Credit',
            'discount_type': 'fixed',
            'discount_value': 30.0,
            'scope': 'whole_subscription',
            'max_usage_limit': 1,
        })

        billing_date_1 = date(2026, 7, 1)
        sub_cap = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'discount_rule_id': rule_capped.id,
            'start_date': billing_date_1,
            'line_ids': [(0, 0, {
                'product_id': self.product_a.id,
                'quantity': 2.0,
                'price_unit': 100.0,  # 200.00
            })]
        })
        sub_cap.action_confirm()

        # Cycle 1: Eligible, receives discount
        inv1 = sub_cap.action_generate_invoice(target_date=billing_date_1)
        self.assertEqual(len(inv1.invoice_line_ids), 2)
        self.assertEqual(rule_capped.current_usage_count, 1)

        # Post inv1 so sub_cap can generate next invoice without draft conflict
        inv1.action_post()

        # Cycle 2: Cap exhausted (current_usage_count == max_usage_limit)
        billing_date_2 = billing_date_1 + relativedelta(months=1)
        inv2 = sub_cap.action_generate_invoice(target_date=billing_date_2)
        # Should contain ONLY product line, NO discount line
        self.assertEqual(len(inv2.invoice_line_ids), 1)
        self.assertEqual(inv2.invoice_line_ids[0].price_unit, 100.0)

        # 2. Date Expiry Test (end_date = 2026-07-31)
        rule_exp = self.DiscountRuleModel.with_user(self.admin_user).create({
            'name': 'July Promo Only',
            'discount_type': 'percentage',
            'discount_value': 20.0,
            'scope': 'whole_subscription',
            'start_date': date(2026, 7, 1),
            'end_date': date(2026, 7, 31),
        })

        sub_exp = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'discount_rule_id': rule_exp.id,
            'start_date': billing_date_1,
            'line_ids': [(0, 0, {
                'product_id': self.product_a.id,
                'quantity': 1.0,
                'price_unit': 100.0,
            })]
        })
        sub_exp.action_confirm()

        # In July -> eligible
        inv_july = sub_exp.action_generate_invoice(target_date=date(2026, 7, 15))
        self.assertEqual(len(inv_july.invoice_line_ids), 2)
        inv_july.action_post()

        # In August -> expired, no discount line
        inv_august = sub_exp.action_generate_invoice(target_date=date(2026, 8, 15))
        self.assertEqual(len(inv_august.invoice_line_ids), 1)
        self.assertEqual(inv_august.invoice_line_ids[0].price_unit, 100.0)
