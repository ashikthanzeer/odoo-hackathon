# -*- coding: utf-8 -*-
from datetime import date
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SubscriptionPlan(models.Model):
    _name = 'subscription.plan'
    _description = 'Brightloop Subscription Plan'
    _order = 'name, id'

    name = fields.Char(
        string='Plan Name',
        required=True,
        translate=True,
        help='Display name of the subscription plan (e.g. Pro Monthly, Enterprise Yearly).'
    )
    code = fields.Char(
        string='Plan Code',
        required=True,
        copy=False,
        help='Unique short identifier for the plan (e.g. PRO-M, ENT-Y).'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Set to false to archive the plan without deleting historical subscriptions.'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )

    # Billing Cycle Configuration
    billing_cycle_unit = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ], string='Billing Cycle Unit', default='monthly', required=True,
       help='Specifies recurrence frequency: Daily, Weekly, Monthly, or Yearly.')

    billing_interval = fields.Integer(
        string='Billing Interval',
        default=1,
        required=True,
        help='Number of billing cycle units between successive recurring invoices (e.g. 1 month, 3 months, 1 year).'
    )

    # Minimum Quantity and Validity Dates
    min_quantity = fields.Float(
        string='Minimum Quantity',
        default=1.0,
        required=True,
        help='Minimum required seats or units for subscriptions under this plan.'
    )
    start_date = fields.Date(
        string='Available From',
        help='Earliest date on which this plan is available for new subscriptions.'
    )
    end_date = fields.Date(
        string='Available Until',
        help='Latest date on which this plan is available for new subscriptions.'
    )

    # Lifecycle Behavioral Policies
    auto_close_on_end = fields.Boolean(
        string='Auto Close On End',
        default=False,
        help='If checked, subscriptions under this plan close automatically when they reach their expiry date.'
    )
    allow_close_early = fields.Boolean(
        string='Allow Close Early',
        default=True,
        help='If checked, customers and staff are permitted to close or terminate the subscription before its scheduled end date.'
    )
    allow_pause = fields.Boolean(
        string='Allow Pause',
        default=True,
        help='If checked, subscriptions under this plan can be paused/suspended temporarily.'
    )
    allow_renewal = fields.Boolean(
        string='Allow Renewal',
        default=True,
        help='If checked, subscriptions under this plan can be renewed when their term ends.'
    )

    description = fields.Text(
        string='Plan Terms & Description',
        translate=True,
        help='Public description and terms shown to customers on quotes and portal.'
    )

    _code_company_unique = models.Constraint(
        'UNIQUE (code, company_id)',
        'The Plan Code must be unique per company!'
    )

    @api.constrains('billing_interval')
    def _check_billing_interval(self):
        for plan in self:
            if plan.billing_interval <= 0:
                raise ValidationError(_(
                    'Billing Interval must be a positive integer strictly greater than zero (found %s).'
                ) % plan.billing_interval)

    @api.constrains('min_quantity')
    def _check_min_quantity(self):
        for plan in self:
            if plan.min_quantity <= 0:
                raise ValidationError(_(
                    'Minimum Quantity must be greater than zero (found %s).'
                ) % plan.min_quantity)

    @api.constrains('start_date', 'end_date')
    def _check_validity_dates(self):
        for plan in self:
            if plan.start_date and plan.end_date and plan.end_date < plan.start_date:
                raise ValidationError(_(
                    'Plan "%s": Available Until date (%s) cannot be earlier than Available From date (%s).'
                ) % (plan.name, plan.end_date, plan.start_date))

    def is_valid_on_date(self, target_date=None):
        """Checks if plan is active and within validity date window on given date."""
        self.ensure_one()
        if not self.active:
            return False
        target = target_date or fields.Date.context_today(self)
        if self.start_date and target < self.start_date:
            return False
        if self.end_date and target > self.end_date:
            return False
        return True

    def validate_quantity(self, quantity):
        """Verifies given quantity meets plan minimum quantity requirement."""
        self.ensure_one()
        if quantity < self.min_quantity:
            raise ValidationError(_(
                'Plan "%s" requires a minimum quantity of %g (requested: %g).'
            ) % (self.name, self.min_quantity, quantity))
        return True

    def calculate_next_date(self, current_date):
        """Computes next recurring billing date based on recurrence unit and interval."""
        self.ensure_one()
        if not current_date:
            current_date = fields.Date.today()
        step = self.billing_interval
        if self.billing_cycle_unit == 'daily':
            return current_date + relativedelta(days=step)
        elif self.billing_cycle_unit == 'weekly':
            return current_date + relativedelta(weeks=step)
        elif self.billing_cycle_unit == 'monthly':
            return current_date + relativedelta(months=step)
        elif self.billing_cycle_unit == 'yearly':
            return current_date + relativedelta(years=step)
        return current_date + relativedelta(months=step)
