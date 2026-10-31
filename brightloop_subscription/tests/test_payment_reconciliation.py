# -*- coding: utf-8 -*-
from datetime import date
from dateutil.relativedelta import relativedelta
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestPaymentReconciliation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.PlanModel = cls.env['subscription.plan']
        cls.SubscriptionModel = cls.env['subscription.subscription']
        cls.ProductTemplate = cls.env['product.template']
        cls.PartnerModel = cls.env['res.partner']
        cls.MoveModel = cls.env['account.move']

        # Setup Customer
        cls.customer = cls.PartnerModel.create({
            'name': 'Brightloop Payment Customer',
            'email': 'payment_test@brightloop.test',
            'is_subscription_customer': True,
        })

        # Setup Monthly Plan allowing renewal and auto close on end
        cls.monthly_plan = cls.PlanModel.create({
            'name': 'Monthly Cloud Plan with Renewal',
            'code': 'MCP-RENEW',
            'billing_cycle_unit': 'monthly',
            'billing_interval': 1,
            'min_quantity': 1.0,
            'allow_renewal': True,
            'auto_close_on_end': True,
        })

        # Setup Fixed Term Plan disallowing renewal
        cls.fixed_plan = cls.PlanModel.create({
            'name': 'Fixed 6-Month Plan No Renewal',
            'code': 'F6M-NORENEW',
            'billing_cycle_unit': 'monthly',
            'billing_interval': 1,
            'min_quantity': 1.0,
            'allow_renewal': False,
            'auto_close_on_end': True,
        })

        # Setup Product
        cls.product_tmpl = cls.ProductTemplate.create({
            'name': 'Cloud Database Enterprise',
            'detailed_type': 'service',
            'list_price': 250.0,
            'is_subscription': True,
        })
        cls.product = cls.product_tmpl.product_variant_id

    def test_01_draft_payment_status_without_invoices(self):
        """Verify new subscription without posted invoices is in draft payment status."""
        today = date(2026, 7, 1)
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 250.0,
            })]
        })
        sub.action_confirm()

        self.assertEqual(sub.payment_status, 'draft')
        self.assertEqual(sub.paid_amount, 0.0)
        self.assertEqual(sub.amount_due, 0.0)
        self.assertEqual(sub.payment_count, 0)

    def test_02_pending_status_on_posted_invoice(self):
        """Verify generating and posting an invoice transitions payment status to pending."""
        today = fields.Date.context_today(self.env.user)
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 2.0,
                'price_unit': 250.0,  # 500.00
            })]
        })
        sub.action_confirm()

        invoice = sub.action_generate_invoice(target_date=today)
        invoice.action_post()

        sub._compute_payment_metrics()
        self.assertEqual(sub.payment_status, 'pending')
        self.assertEqual(sub.paid_amount, 0.0)
        self.assertEqual(sub.amount_due, 500.0)

    def test_03_partial_and_paid_status_transitions(self):
        """Verify status transitions from partial payment to fully paid."""
        today = fields.Date.context_today(self.env.user)
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 250.0,
            })]
        })
        sub.action_confirm()

        invoice = sub.action_generate_invoice(target_date=today)
        invoice.action_post()

        # Simulate partial payment (received 100 out of 250)
        invoice.sudo().write({
            'payment_state': 'partial',
            'amount_residual': 150.0,
        })
        sub._compute_payment_metrics()
        self.assertEqual(sub.payment_status, 'partial')
        self.assertEqual(sub.paid_amount, 100.0)
        self.assertEqual(sub.amount_due, 150.0)

        # Simulate full settlement
        invoice.sudo().write({
            'payment_state': 'paid',
            'amount_residual': 0.0,
        })
        sub._compute_payment_metrics()
        self.assertEqual(sub.payment_status, 'paid')
        self.assertEqual(sub.paid_amount, 250.0)
        self.assertEqual(sub.amount_due, 0.0)

    def test_04_overdue_status_when_past_due_date(self):
        """Verify status is marked overdue when posted invoice is past its due date."""
        today = fields.Date.context_today(self.env.user)
        past_date = today - relativedelta(days=10)

        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'start_date': past_date,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 250.0,
            })]
        })
        sub.action_confirm()

        invoice = sub.action_generate_invoice(target_date=past_date)
        invoice.action_post()

        # Set invoice due date in the past
        invoice.sudo().write({
            'invoice_date_due': past_date + relativedelta(days=5),  # 5 days ago
            'amount_residual': 250.0,
            'payment_state': 'not_paid',
        })
        sub._compute_payment_metrics()
        self.assertEqual(sub.payment_status, 'overdue')
        self.assertEqual(sub.amount_due, 250.0)

    def test_05_contract_renewal_lifecycle(self):
        """Verify contract renewal extends expiry date for allowed plans and rejects disallowed plans."""
        today = date(2026, 8, 1)
        initial_expiry = date(2026, 8, 31)

        # 1. Plan allowing renewal
        sub_renew = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'start_date': today,
            'expiry_date': initial_expiry,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 250.0,
            })]
        })
        sub_renew.action_confirm()

        sub_renew.action_renew()
        expected_expiry = initial_expiry + relativedelta(months=1)
        self.assertEqual(sub_renew.expiry_date, expected_expiry)

        # 2. Plan disallowing renewal
        sub_fixed = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.fixed_plan.id,
            'start_date': today,
            'expiry_date': initial_expiry,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 250.0,
            })]
        })
        sub_fixed.action_confirm()

        with self.assertRaises(ValidationError):
            sub_fixed.action_renew()

    def test_06_cron_contract_expiries_auto_closure(self):
        """Verify cron job auto-closes expired contracts when all balances are settled."""
        today = fields.Date.context_today(self.env.user)

        sub_settled = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'start_date': today - relativedelta(months=1),
            'expiry_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 250.0,
            })]
        })
        sub_settled.action_confirm()
        self.assertEqual(sub_settled.state, 'active')

        # Run cron: with zero balance due, it should auto-close
        closed_count = self.SubscriptionModel._cron_process_contract_expiries()
        self.assertGreaterEqual(closed_count, 1)
        self.assertEqual(sub_settled.state, 'closed')

    def test_07_cron_contract_expiries_prevent_closure_when_unpaid(self):
        """Verify cron job does NOT auto-close expired contracts that have outstanding unpaid invoices."""
        today = fields.Date.context_today(self.env.user)
        past_date = today - relativedelta(months=1)

        sub_unpaid = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'start_date': past_date,
            'expiry_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 250.0,
            })]
        })
        sub_unpaid.action_confirm()

        # Generate invoice and leave residual
        inv = sub_unpaid.action_generate_invoice(target_date=past_date)
        inv.action_post()
        inv.sudo().write({'amount_residual': 250.0})

        # Run expiry cron
        self.SubscriptionModel._cron_process_contract_expiries()
        # Must NOT be closed due to unpaid debt
        self.assertEqual(sub_unpaid.state, 'active')
        self.assertEqual(sub_unpaid.amount_due, 250.0)

    def test_08_payments_smart_button_action(self):
        """Verify clicking payments action returns valid account.payment act_window."""
        today = fields.Date.context_today(self.env.user)
        sub = self.SubscriptionModel.create({
            'partner_id': self.customer.id,
            'plan_id': self.monthly_plan.id,
            'start_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 250.0,
            })]
        })
        sub.action_confirm()

        action = sub.action_view_payments()
        self.assertIsInstance(action, dict)
        self.assertEqual(action.get('res_model'), 'account.payment')
