# -*- coding: utf-8 -*-
from odoo import models, fields, tools


class SubscriptionReport(models.Model):
    _name = 'subscription.report'
    _description = 'Subscription Analytics Report'
    _auto = False
    _rec_name = 'subscription_id'
    _order = 'mrr desc'

    subscription_id = fields.Many2one('subscription.subscription', string='Subscription', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', readonly=True)
    user_id = fields.Many2one('res.users', string='Salesperson', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('quotation', 'Quotation'),
        ('confirmed', 'Confirmed'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('closed', 'Closed'),
    ], string='Status', readonly=True)

    payment_status = fields.Selection([
        ('draft', 'Draft / No Invoices'),
        ('pending', 'Pending Payment'),
        ('partial', 'Partially Paid'),
        ('paid', 'Fully Paid'),
        ('overdue', 'Overdue'),
    ], string='Payment Status', readonly=True)

    billing_cycle_unit = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ], string='Billing Unit', readonly=True)

    start_date = fields.Date(string='Start Date', readonly=True)
    expiry_date = fields.Date(string='Expiry Date', readonly=True)
    next_billing_date = fields.Date(string='Next Billing Date', readonly=True)

    total_quantity = fields.Float(string='Total Quantity / Seats', readonly=True)
    amount_untaxed = fields.Monetary(string='Untaxed Amount', readonly=True, currency_field='currency_id')
    amount_tax = fields.Monetary(string='Taxes', readonly=True, currency_field='currency_id')
    amount_total = fields.Monetary(string='Gross Total', readonly=True, currency_field='currency_id')
    discount_amount = fields.Monetary(string='Discount Amount', readonly=True, currency_field='currency_id')
    amount_net = fields.Monetary(string='Net Total', readonly=True, currency_field='currency_id')
    paid_amount = fields.Monetary(string='Paid Amount', readonly=True, currency_field='currency_id')
    amount_due = fields.Monetary(string='Balance Due', readonly=True, currency_field='currency_id')
    mrr = fields.Monetary(string='MRR', readonly=True, currency_field='currency_id')
    arr = fields.Monetary(string='ARR', readonly=True, currency_field='currency_id')
    nbr_subscriptions = fields.Integer(string='# of Subscriptions', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE or REPLACE VIEW %s AS (
                SELECT
                    sub.id AS id,
                    sub.id AS subscription_id,
                    sub.partner_id AS partner_id,
                    sub.plan_id AS plan_id,
                    sub.user_id AS user_id,
                    sub.company_id AS company_id,
                    sub.currency_id AS currency_id,
                    sub.state AS state,
                    sub.payment_status AS payment_status,
                    plan.billing_cycle_unit AS billing_cycle_unit,
                    sub.start_date AS start_date,
                    sub.expiry_date AS expiry_date,
                    sub.next_billing_date AS next_billing_date,
                    COALESCE(sub.total_quantity, 0.0) AS total_quantity,
                    COALESCE(sub.amount_untaxed, 0.0) AS amount_untaxed,
                    COALESCE(sub.amount_tax, 0.0) AS amount_tax,
                    COALESCE(sub.amount_total, 0.0) AS amount_total,
                    COALESCE(sub.discount_amount, 0.0) AS discount_amount,
                    COALESCE(sub.amount_net, 0.0) AS amount_net,
                    COALESCE(sub.paid_amount, 0.0) AS paid_amount,
                    COALESCE(sub.amount_due, 0.0) AS amount_due,
                    COALESCE(sub.mrr, 0.0) AS mrr,
                    COALESCE(sub.arr, 0.0) AS arr,
                    1 AS nbr_subscriptions
                FROM
                    subscription_subscription sub
                JOIN
                    subscription_plan plan ON plan.id = sub.plan_id
            )
        """ % self._table)
