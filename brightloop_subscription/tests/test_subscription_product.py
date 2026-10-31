# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestSubscriptionProduct(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ProductTemplate = cls.env['product.template']
        cls.ProductProduct = cls.env['product.product']
        cls.ProductAttribute = cls.env['product.attribute']
        cls.ProductAttributeValue = cls.env['product.attribute.value']
        cls.PlanModel = cls.env['subscription.plan']

        # Create a sample plan
        cls.plan = cls.PlanModel.create({
            'name': 'Test Monthly Plan',
            'code': 'TMP-01',
            'billing_cycle_unit': 'monthly',
            'billing_interval': 1,
            'min_quantity': 1.0,
        })

        # Create Brand attribute
        cls.attr_brand = cls.ProductAttribute.create({
            'name': 'Brand',
            'create_variant': 'always',
        })
        cls.val_standard = cls.ProductAttributeValue.create({
            'name': 'Standard Brand',
            'attribute_id': cls.attr_brand.id,
        })
        cls.val_odoo = cls.ProductAttributeValue.create({
            'name': 'Odoo Brand',
            'attribute_id': cls.attr_brand.id,
        })

    def test_01_create_subscription_product_template(self):
        """Verify product template fields for subscription."""
        template = self.ProductTemplate.create({
            'name': 'Brightloop Core CRM',
            'detailed_type': 'service',
            'list_price': 1200.0,
            'standard_price': 400.0,
            'is_subscription': True,
            'subscription_plan_id': self.plan.id,
            'description_sale': 'Cloud CRM software with 99.9% uptime SLA.',
        })
        self.assertTrue(template.is_subscription)
        self.assertEqual(template.list_price, 1200.0)
        self.assertEqual(template.standard_price, 400.0)
        self.assertEqual(template.subscription_plan_id, self.plan)

    def test_02_variant_additional_pricing(self):
        """Verify Odoo brand attribute adds 560 to base sales price."""
        template = self.ProductTemplate.create({
            'name': 'Brightloop Platform Enterprise',
            'detailed_type': 'service',
            'list_price': 1000.0,
            'standard_price': 350.0,
            'is_subscription': True,
            'subscription_plan_id': self.plan.id,
            'attribute_line_ids': [(0, 0, {
                'attribute_id': self.attr_brand.id,
                'value_ids': [(6, 0, [self.val_standard.id, self.val_odoo.id])]
            })]
        })

        # Set price_extra = 560 for Odoo brand attribute value on this template
        ptav_odoo = template.attribute_line_ids.product_template_value_ids.filtered(
            lambda v: v.product_attribute_value_id == self.val_odoo
        )
        self.assertTrue(ptav_odoo)
        ptav_odoo.write({'price_extra': 560.0})

        # Check variants generated
        variants = self.ProductProduct.search([('product_tmpl_id', '=', template.id)])
        self.assertEqual(len(variants), 2)

        standard_variant = variants.filtered(
            lambda v: self.val_standard in v.product_template_attribute_value_ids.product_attribute_value_id
        )
        odoo_variant = variants.filtered(
            lambda v: self.val_odoo in v.product_template_attribute_value_ids.product_attribute_value_id
        )

        # Standard variant should be base price: 1000.0
        self.assertEqual(standard_variant.lst_price, 1000.0)
        self.assertEqual(standard_variant.subscription_effective_price, 1000.0)

        # Odoo brand variant should be base price + 560 = 1560.0
        self.assertEqual(odoo_variant.lst_price, 1560.0)
        self.assertEqual(odoo_variant.subscription_effective_price, 1560.0)
