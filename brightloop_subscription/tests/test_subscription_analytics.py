# -*- coding: utf-8 -*-
from datetime import date
from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError


class TestSubscriptionAnalytics(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.PlanModel = cls.env['subscription.plan']
        cls.SubscriptionModel = cls.env['subscription.subscription']
        cls.ProductTemplate = cls.env['product.template']
        cls.PartnerModel = cls.env['res.partner']
        cls.DiscountModel = cls.env['subscription.discount.rule']
        cls.ReportModel = cls.env['subscription.report']
        cls.UserModel = cls.env['res.users']

        # Setup Partner
        cls.customer = cls.PartnerModel.create({
            'name': 'Brightloop Analytics Customer',
            'email': 'analytics_test@brightloop.test',
            'is_subscription_customer': True,
        })

        # Setup Plans across all billing cycle units
        cls.monthly_plan = cls.PlanModel.create({
            'name': 'Analytics Monthly Plan',
            'code': 'ANL-M1',
            'billing_cycle_unit': 'monthly',
            'billing_interval': 1,
            'min_quantity': 1.0,
        })

        cls.quarterly_plan = cls.PlanModel.create({
            'name': 'Analytics Quarterly Plan',
            'code': 'ANL-Q3',
            'billing_cycle_unit': 'monthly',
            'billing_interval': 3,
            'min_quantity': 1.0,
        })

        cls.yearly_plan = cls.PlanModel.create({
            'name': 'Analytics Yearly Plan',
            'code': 'ANL-Y1',
            'billing_cycle_unit': 'yearly',
            'billing_interval': 1,
            'min_quantity': 1.0,
        })

        cls.weekly_plan = cls.PlanModel.create({
            'name': 'Analytics Weekly Plan',
            'code': 'ANL-W1',
            'billing_cycle_unit': 'weekly',
            'billing_interval': 1,
            'min_quantity': 1.0,
        })

        cls.daily_plan = cls.PlanModel.create({
            'name': 'Analytics Daily Plan',
            'code': 'ANL-D1',
            'billing_cycle_unit': 'daily',
            'billing_interval': 1,
            'min_quantity': 1.0,
        })

        # Setup Product
        cls.product_tmpl = cls.ProductTemplate.create({
            'name': 'Analytics Test Service',
            'detailed_type': 'service',
            'list_price': 100.0,
            'is_subscription': True,
        })
        cls.product = cls.product_tmpl.product_variant_id

        # Setup Sales User
        cls.group_user = cls.env.ref('brightloop_subscription.group_subscription_user')
        cls.sales_user = cls.UserModel.create({
            'name': 'Analytics Sales Rep',
            'login': 'analytics_rep@brightloop.test',
            'email': 'analytics_rep@brightloop.test',
            'groups_id': [(6, 0, [cls.group_user.id, cls.env.ref('base.group_user').id])],
        })

    def test_01_recurring_revenue_normalization_all_units(self):
        """Verify MRR and ARR formulas for monthly, quarterly, yearly, weekly, and daily cycles."""
        today = date(2026, 9, 1)

        # 1. Monthly (interval 1, net 250.00) -> MRR = 250.00, ARR = 3000.00
        sub_monthly = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 2.5,
                'price_unit': 100.0,  # 250.00
            })]
        })
        self.assertEqual(sub_monthly.amount_net, 250.0)
        self.assertEqual(sub_monthly.mrr, 250.0)
        self.assertEqual(sub_monthly.arr, 3000.0)

        # 2. Quarterly (interval 3 months, net 600.00) -> MRR = 200.00, ARR = 2400.00
        sub_quarterly = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.quarterly_plan.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 6.0,
                'price_unit': 100.0,  # 600.00
            })]
        })
        self.assertEqual(sub_quarterly.amount_net, 600.0)
        self.assertEqual(sub_quarterly.mrr, 200.0)
        self.assertEqual(sub_quarterly.arr, 2400.0)

        # 3. Yearly (interval 1 year, net 1200.00) -> MRR = 100.00, ARR = 1200.00
        sub_yearly = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.yearly_plan.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 12.0,
                'price_unit': 100.0,  # 1200.00
            })]
        })
        self.assertEqual(sub_yearly.amount_net, 1200.0)
        self.assertEqual(sub_yearly.mrr, 100.0)
        self.assertEqual(sub_yearly.arr, 1200.0)

        # 4. Weekly (interval 1 week, net 50.00) -> ARR = 2600.00, MRR = 216.67
        sub_weekly = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.weekly_plan.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 0.5,
                'price_unit': 100.0,  # 50.00
            })]
        })
        self.assertEqual(sub_weekly.amount_net, 50.0)
        self.assertEqual(sub_weekly.arr, 2600.0)
        self.assertEqual(sub_weekly.mrr, 216.67)

        # 5. Daily (interval 1 day, net 10.00) -> MRR = 300.00, ARR = 3650.00
        sub_daily = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.daily_plan.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 0.1,
                'price_unit': 100.0,  # 10.00
            })]
        })
        self.assertEqual(sub_daily.amount_net, 10.0)
        self.assertEqual(sub_daily.mrr, 300.0)
        self.assertEqual(sub_daily.arr, 3650.0)

    def test_02_discount_impact_on_mrr_and_arr(self):
        """Verify that applying a discount rule reduces amount_net and updates MRR/ARR accordingly."""
        rule = self.DiscountModel.create({
            'name': '10% Launch Promo',
            'discount_type': 'percentage',
            'discount_value': 10.0,
            'scope': 'whole_subscription',
        })

        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'discount_rule_id': rule.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 10.0,
                'price_unit': 100.0,  # 1000.00 untaxed
            })]
        })
        # Net total should be 1000 - 100 = 900.00
        self.assertEqual(sub.discount_amount, 100.0)
        self.assertEqual(sub.amount_net, 900.0)
        # Normalized MRR and ARR reflect discounted net base
        self.assertEqual(sub.mrr, 900.0)
        self.assertEqual(sub.arr, 10800.0)

    def test_03_subscription_report_query(self):
        """Verify querying subscription.report SQL view aggregates correct dimensions and metrics."""
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 5.0,
                'price_unit': 100.0,
            })]
        })
        sub.action_confirm()

        report_records = self.ReportModel.search([('subscription_id', '=', sub.id)])
        self.assertTrue(report_records)
        report_row = report_records[0]

        self.assertEqual(report_row.partner_id, self.customer)
        self.assertEqual(report_row.plan_id, self.monthly_plan)
        self.assertEqual(report_row.billing_cycle_unit, 'monthly')
        self.assertEqual(report_row.mrr, 500.0)
        self.assertEqual(report_row.arr, 6000.0)
        self.assertEqual(report_row.nbr_subscriptions, 1)

    def test_04_reporting_read_access_for_sales_rep(self):
        """Verify sales staff user can read subscription.report without AccessError."""
        # Query with sales rep user context
        reports = self.ReportModel.with_user(self.sales_user).search([])
        self.assertIsInstance(reports.ids, list)
