# -*- coding: utf-8 -*-
from datetime import date
from dateutil.relativedelta import relativedelta
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestSubscriptionPlan(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.PlanModel = cls.env['subscription.plan']

    def test_01_create_valid_monthly_plan(self):
        """Verify successful creation of monthly plan with lifecycle policies."""
        plan = self.PlanModel.create({
            'name': 'Pro Cloud Monthly',
            'code': 'PCM-01',
            'billing_cycle_unit': 'monthly',
            'billing_interval': 1,
            'min_quantity': 2.0,
            'start_date': date(2026, 1, 1),
            'end_date': date(2026, 12, 31),
            'auto_close_on_end': True,
            'allow_close_early': False,
            'allow_pause': True,
            'allow_renewal': True,
        })
        self.assertEqual(plan.name, 'Pro Cloud Monthly')
        self.assertEqual(plan.min_quantity, 2.0)
        self.assertTrue(plan.auto_close_on_end)
        self.assertFalse(plan.allow_close_early)

    def test_02_invalid_billing_interval_rejected(self):
        """Verify billing interval <= 0 is rejected."""
        with self.assertRaises(ValidationError):
            self.PlanModel.create({
                'name': 'Invalid Interval Plan',
                'code': 'IIP-01',
                'billing_cycle_unit': 'monthly',
                'billing_interval': 0,
                'min_quantity': 1.0,
            })

    def test_03_invalid_min_quantity_rejected(self):
        """Verify minimum quantity <= 0 is rejected."""
        with self.assertRaises(ValidationError):
            self.PlanModel.create({
                'name': 'Invalid Min Qty Plan',
                'code': 'IMQ-01',
                'billing_cycle_unit': 'weekly',
                'billing_interval': 1,
                'min_quantity': 0.0,
            })

    def test_04_invalid_date_range_rejected(self):
        """Verify end_date < start_date is rejected."""
        with self.assertRaises(ValidationError):
            self.PlanModel.create({
                'name': 'Invalid Dates Plan',
                'code': 'IDP-01',
                'billing_cycle_unit': 'yearly',
                'billing_interval': 1,
                'min_quantity': 1.0,
                'start_date': date(2026, 6, 1),
                'end_date': date(2026, 5, 1),  # earlier than start_date
            })

    def test_05_plan_validity_on_dates(self):
        """Verify plan validity checking within and outside date range."""
        plan = self.PlanModel.create({
            'name': 'Summer Special Plan',
            'code': 'SSP-2026',
            'billing_cycle_unit': 'monthly',
            'billing_interval': 1,
            'min_quantity': 1.0,
            'start_date': date(2026, 6, 1),
            'end_date': date(2026, 8, 31),
        })
        self.assertTrue(plan.is_valid_on_date(date(2026, 7, 15)))
        self.assertFalse(plan.is_valid_on_date(date(2026, 5, 31)))
        self.assertFalse(plan.is_valid_on_date(date(2026, 9, 1)))

    def test_06_quantity_validation(self):
        """Verify plan minimum quantity validation method."""
        plan = self.PlanModel.create({
            'name': 'Team Enterprise Plan',
            'code': 'TEP-05',
            'billing_cycle_unit': 'yearly',
            'billing_interval': 1,
            'min_quantity': 5.0,
        })
        self.assertTrue(plan.validate_quantity(5.0))
        self.assertTrue(plan.validate_quantity(10.0))
        with self.assertRaises(ValidationError):
            plan.validate_quantity(4.0)

    def test_07_calculate_next_billing_date(self):
        """Verify calculation of next billing date across all recurrence types."""
        base_date = date(2026, 1, 15)

        daily_plan = self.PlanModel.create({
            'name': 'Daily Recurrence',
            'code': 'DR-01',
            'billing_cycle_unit': 'daily',
            'billing_interval': 3,
            'min_quantity': 1.0,
        })
        self.assertEqual(daily_plan.calculate_next_date(base_date), date(2026, 1, 18))

        weekly_plan = self.PlanModel.create({
            'name': 'Weekly Recurrence',
            'code': 'WR-01',
            'billing_cycle_unit': 'weekly',
            'billing_interval': 2,
            'min_quantity': 1.0,
        })
        self.assertEqual(weekly_plan.calculate_next_date(base_date), date(2026, 1, 29))

        monthly_plan = self.PlanModel.create({
            'name': 'Monthly Recurrence',
            'code': 'MR-01',
            'billing_cycle_unit': 'monthly',
            'billing_interval': 1,
            'min_quantity': 1.0,
        })
        self.assertEqual(monthly_plan.calculate_next_date(base_date), date(2026, 2, 15))

        yearly_plan = self.PlanModel.create({
            'name': 'Yearly Recurrence',
            'code': 'YR-01',
            'billing_cycle_unit': 'yearly',
            'billing_interval': 1,
            'min_quantity': 1.0,
        })
        self.assertEqual(yearly_plan.calculate_next_date(base_date), date(2027, 1, 15))
