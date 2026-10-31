# -*- coding: utf-8 -*-
from datetime import date
from dateutil.relativedelta import relativedelta
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestQuotationTemplate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.PlanModel = cls.env['subscription.plan']
        cls.TemplateModel = cls.env['subscription.quotation.template']
        cls.SubscriptionModel = cls.env['subscription.subscription']
        cls.ProductTemplate = cls.env['product.template']
        cls.PartnerModel = cls.env['res.partner']

        # Setup Customer
        cls.customer = cls.PartnerModel.create({
            'name': 'Brightloop Client Ltd',
            'email': 'client@brightloop.test',
            'is_subscription_customer': True
        })

        # Setup Plan
        cls.plan = cls.PlanModel.create({
            'name': 'Pro Monthly Plan',
            'code': 'PMP-TEST',
            'billing_cycle_unit': 'monthly',
            'billing_interval': 1,
            'min_quantity': 2.0,
        })

        # Setup Product
        cls.product_tmpl = cls.ProductTemplate.create({
            'name': 'Cloud Collaboration Suite',
            'type': 'service',
            'list_price': 150.0,
            'is_subscription': True,
        })
        cls.product = cls.product_tmpl.product_variant_id

    def test_01_create_quotation_template(self):
        """Verify quotation template configuration with lines and validity."""
        template = self.TemplateModel.create({
            'name': '14-Day Pilot Offer',
            'plan_id': self.plan.id,
            'validity_days': 14,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.display_name,
                'quantity': 5.0,
                'price_unit': 140.0,
            })]
        })
        self.assertEqual(template.validity_days, 14)
        self.assertEqual(len(template.line_ids), 1)
        self.assertEqual(template.line_ids[0].quantity, 5.0)

    def test_02_invalid_validity_days(self):
        """Verify validity_days <= 0 is rejected."""
        with self.assertRaises(ValidationError):
            self.TemplateModel.create({
                'name': 'Zero Days Template',
                'plan_id': self.plan.id,
                'validity_days': 0,
            })

    def test_03_apply_template_to_subscription(self):
        """Verify selecting a quotation template pre-populates plan, expiry date, and lines."""
        template = self.TemplateModel.create({
            'name': 'Standard 30-Day Offer',
            'plan_id': self.plan.id,
            'validity_days': 30,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Cloud Collaboration Pilot',
                'quantity': 3.0,
                'price_unit': 150.0,
            })]
        })

        start = date(2026, 4, 1)
        sub = self.SubscriptionModel.new({
            'partner_id': self.customer.id,
            'start_date': start,
            'template_id': template.id,
        })
        # Trigger onchange
        sub._onchange_template_id()

        self.assertEqual(sub.plan_id, self.plan)
        self.assertEqual(sub.expiry_date, start + relativedelta(days=30))
        self.assertEqual(len(sub.line_ids), 1)
        self.assertEqual(sub.line_ids[0].product_id, self.product)
        self.assertEqual(sub.line_ids[0].quantity, 3.0)
        self.assertEqual(sub.line_ids[0].price_unit, 150.0)
