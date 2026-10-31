# -*- coding: utf-8 -*-
from datetime import date
from dateutil.relativedelta import relativedelta
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestSubscriptionLifecycle(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.PlanModel = cls.env['subscription.plan']
        cls.SubscriptionModel = cls.env['subscription.subscription']
        cls.ProductTemplate = cls.env['product.template']
        cls.PartnerModel = cls.env['res.partner']
        cls.TaxModel = cls.env['account.tax']

        # Customer
        cls.customer = cls.PartnerModel.create({
            'name': 'Brightloop Enterprise Corp',
            'email': 'enterprise@brightloop.test',
            'is_subscription_customer': True
        })

        # Tax (10%)
        tax_group = cls.env['account.tax.group'].search([], limit=1) or cls.env['account.tax.group'].create({'name': 'Test Tax Group'})
        country = cls.env.company.account_fiscal_country_id or cls.env['res.country'].search([], limit=1)
        if not cls.env.company.account_fiscal_country_id:
            cls.env.company.account_fiscal_country_id = country.id
        cls.tax_10 = cls.TaxModel.create({
            'name': 'Test VAT 10%',
            'amount_type': 'percent',
            'amount': 10.0,
            'type_tax_use': 'sale',
            'tax_group_id': tax_group.id,
            'country_id': country.id,
        })

        # Product
        cls.product_tmpl = cls.ProductTemplate.create({
            'name': 'Brightloop ERP Core',
            'type': 'service',
            'list_price': 500.0,
            'is_subscription': True,
        })
        cls.product = cls.product_tmpl.product_variant_id

        # Standard Plan (allows pause and early close, min qty 3)
        cls.standard_plan = cls.PlanModel.create({
            'name': 'Standard Flexible Plan',
            'code': 'SFP-01',
            'billing_cycle_unit': 'monthly',
            'billing_interval': 1,
            'min_quantity': 3.0,
            'allow_pause': True,
            'allow_close_early': True,
        })

        # Strict Plan (disallows pause, disallows early close, min qty 5)
        cls.strict_plan = cls.PlanModel.create({
            'name': 'Strict Annual Contract',
            'code': 'SAC-01',
            'billing_cycle_unit': 'yearly',
            'billing_interval': 1,
            'min_quantity': 5.0,
            'allow_pause': False,
            'allow_close_early': False,
        })

    def test_01_financial_computation_and_taxes(self):
        """Verify line subtotal, tax amount, and grand total calculations."""
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.standard_plan.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.display_name,
                'quantity': 10.0,
                'price_unit': 500.0,
                'tax_ids': [(6, 0, [self.tax_10.id])],
            })]
        })

        # 10 * 500 = 5000 untaxed, 10% tax = 500, total = 5500
        self.assertEqual(sub.amount_untaxed, 5000.0)
        self.assertEqual(sub.amount_tax, 500.0)
        self.assertEqual(sub.amount_total, 5500.0)

    def test_02_minimum_quantity_enforcement(self):
        """Verify confirming subscription below plan minimum quantity is rejected."""
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.standard_plan.id,  # min_quantity = 3
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.display_name,
                'quantity': 2.0,  # Below minimum 3!
                'price_unit': 500.0,
            })]
        })

        with self.assertRaises(ValidationError):
            sub.action_confirm()

    def test_03_lifecycle_state_machine_and_sequence(self):
        """Verify full progression: draft -> quotation -> confirmed/active -> closed."""
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.standard_plan.id,
            'start_date': date.today(),
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.display_name,
                'quantity': 4.0,
                'price_unit': 500.0,
            })]
        })
        self.assertEqual(sub.state, 'draft')
        self.assertEqual(sub.name, 'New')

        # Advance to Quotation
        sub.action_quote()
        self.assertEqual(sub.state, 'quotation')

        # Confirm & Activate
        sub.action_confirm()
        self.assertEqual(sub.state, 'active')
        self.assertTrue(sub.name.startswith('SUB/'))

        # Close
        sub.action_close()
        self.assertEqual(sub.state, 'closed')

    def test_04_policy_enforcement_pause_disallowed(self):
        """Verify pausing is blocked when plan.allow_pause is False."""
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.strict_plan.id,
            'start_date': date.today(),
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.display_name,
                'quantity': 5.0,
                'price_unit': 500.0,
            })]
        })
        sub.action_confirm()
        self.assertEqual(sub.state, 'active')

        with self.assertRaises(ValidationError):
            sub.action_pause()

    def test_05_policy_enforcement_early_close_disallowed(self):
        """Verify early closure before expiry date is blocked when plan.allow_close_early is False."""
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.strict_plan.id,
            'start_date': date.today(),
            'expiry_date': date.today() + relativedelta(years=1),
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.display_name,
                'quantity': 5.0,
                'price_unit': 500.0,
            })]
        })
        sub.action_confirm()
        self.assertEqual(sub.state, 'active')

        with self.assertRaises(ValidationError):
            sub.action_close()
