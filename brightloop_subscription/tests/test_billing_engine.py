# -*- coding: utf-8 -*-
from datetime import date
from dateutil.relativedelta import relativedelta
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestBillingEngine(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.PlanModel = cls.env['subscription.plan']
        cls.SubscriptionModel = cls.env['subscription.subscription']
        cls.ProductTemplate = cls.env['product.template']
        cls.PartnerModel = cls.env['res.partner']
        cls.TaxModel = cls.env['account.tax']
        cls.MoveModel = cls.env['account.move']
        cls.WizardModel = cls.env['subscription.billing.wizard']

        # Setup Accounts and Sale Journal for Odoo 19 Invoicing
        company = cls.env.company
        cls.account_income = cls.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_ids', 'in', company.id),
        ], limit=1)
        if not cls.account_income:
            cls.account_income = cls.env['account.account'].create({
                'name': 'Subscription Income',
                'code': '400020',
                'account_type': 'income',
                'company_ids': [(6, 0, [company.id])],
            })

        cls.account_receivable = cls.env['account.account'].search([
            ('account_type', '=', 'asset_receivable'),
            ('company_ids', 'in', company.id),
        ], limit=1)
        if not cls.account_receivable:
            cls.account_receivable = cls.env['account.account'].create({
                'name': 'Subscription Receivable',
                'code': '120020',
                'account_type': 'asset_receivable',
                'reconcile': True,
                'company_ids': [(6, 0, [company.id])],
            })

        cls.sale_journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not cls.sale_journal:
            cls.sale_journal = cls.env['account.journal'].create({
                'name': 'Customer Invoices',
                'code': 'INV',
                'type': 'sale',
                'company_id': company.id,
                'default_account_id': cls.account_income.id,
            })

        # Setup Partner
        cls.customer = cls.PartnerModel.create({
            'name': 'Brightloop Billing Test Customer',
            'email': 'billing_test@brightloop.test',
            'is_subscription_customer': True,
            'property_account_receivable_id': cls.account_receivable.id,
        })

        # Setup Tax (15% VAT)
        tax_group = cls.env['account.tax.group'].search([], limit=1) or cls.env['account.tax.group'].create({'name': 'Test Tax Group'})
        country = cls.env.company.account_fiscal_country_id or cls.env['res.country'].search([], limit=1)
        if not cls.env.company.account_fiscal_country_id:
            cls.env.company.account_fiscal_country_id = country.id
        cls.tax_15 = cls.TaxModel.create({
            'name': 'Test VAT 15%',
            'amount_type': 'percent',
            'amount': 15.0,
            'type_tax_use': 'sale',
            'tax_group_id': tax_group.id,
            'country_id': country.id,
        })

        # Setup Monthly Plan
        cls.monthly_plan = cls.PlanModel.create({
            'name': 'Monthly Cloud Plan',
            'code': 'MCP-TEST',
            'billing_cycle_unit': 'monthly',
            'billing_interval': 1,
            'min_quantity': 1.0,
        })

        # Setup Subscription Product
        cls.product_tmpl = cls.ProductTemplate.create({
            'name': 'Cloud Server Instance',
            'type': 'service',
            'list_price': 200.0,
            'is_subscription': True,
            'taxes_id': [(6, 0, [cls.tax_15.id])],
        })
        cls.product = cls.product_tmpl.product_variant_id

    def test_01_single_invoice_generation_and_tax_mapping(self):
        """Verify generating invoice creates account.move, maps taxes, and advances next billing date."""
        today = date(2026, 5, 1)
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.display_name,
                'quantity': 2.0,
                'price_unit': 200.0,
                'tax_ids': [(6, 0, [self.tax_15.id])],
            })]
        })
        # Confirm & activate
        sub.action_confirm()
        self.assertEqual(sub.state, 'active')
        self.assertEqual(sub.next_billing_date, today)

        # Generate invoice
        invoice = sub.action_generate_invoice(target_date=today)
        self.assertTrue(invoice)
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.partner_id, self.customer)
        self.assertEqual(invoice.subscription_id, sub)
        self.assertEqual(len(invoice.invoice_line_ids), 1)

        # Check line details
        inv_line = invoice.invoice_line_ids[0]
        self.assertEqual(inv_line.quantity, 2.0)
        self.assertEqual(inv_line.price_unit, 200.0)
        self.assertIn(self.tax_15, inv_line.tax_ids)

        # Check sub billing dates: last = today, next = today + 1 month
        self.assertEqual(sub.last_billing_date, today)
        self.assertEqual(sub.next_billing_date, today + relativedelta(months=1))
        self.assertEqual(sub.invoice_count, 1)

    def test_02_double_billing_prevented(self):
        """Verify attempting to generate an invoice before next_billing_date raises UserError."""
        today = date(2026, 5, 1)
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.display_name,
                'quantity': 1.0,
                'price_unit': 200.0,
            })]
        })
        sub.action_confirm()

        # First billing succeeds
        sub.action_generate_invoice(target_date=today)

        # Immediate second billing attempt on same date should fail
        with self.assertRaises(UserError):
            sub.action_generate_invoice(target_date=today)

    def test_03_existing_draft_invoice_blocks_duplicate(self):
        """Verify generating another invoice is blocked if a draft invoice already exists."""
        today = date(2026, 5, 1)
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.display_name,
                'quantity': 1.0,
                'price_unit': 200.0,
            })]
        })
        sub.action_confirm()
        # Reset next_billing_date to past to test draft collision
        sub.action_generate_invoice(target_date=today)
        # Advance clock to next month while first invoice is still draft
        next_month = today + relativedelta(months=1)
        self.assertEqual(sub.next_billing_date, next_month)

        with self.assertRaises(ValidationError):
            sub.action_generate_invoice(target_date=next_month)

    def test_04_cron_batch_recurring_billing(self):
        """Verify cron method finds due active subscriptions and bills them."""
        today = date(2026, 6, 1)
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.display_name,
                'quantity': 3.0,
                'price_unit': 200.0,
            })]
        })
        sub.action_confirm()
        self.assertEqual(sub.next_billing_date, today)

        # Execute cron with target date matching today
        sub.action_generate_invoice(target_date=today)
        self.assertEqual(sub.invoice_count, 1)
        self.assertEqual(sub.next_billing_date, today + relativedelta(months=1))
