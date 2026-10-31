# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError


class SubscriptionDiscountRule(models.Model):
    _name = 'subscription.discount.rule'
    _description = 'Subscription Discount Rule'
    _order = 'name, id'

    name = fields.Char(
        string='Discount Name',
        required=True,
        translate=True,
        help='Display name of the discount rule (e.g. 10+ Seats Volume Discount, New Client Launch Credit).'
    )
    code = fields.Char(
        string='Discount Code',
        copy=False,
        help='Internal promo code or identifier.'
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    discount_type = fields.Selection([
        ('percentage', 'Percentage (%)'),
        ('fixed', 'Fixed Amount'),
    ], string='Discount Type', default='percentage', required=True)

    discount_value = fields.Float(
        string='Discount Value',
        required=True,
        default=10.0,
        digits='Product Price',
        help='Percentage deduction (e.g. 10 for 10%) or flat currency amount (e.g. 50.00).'
    )
    scope = fields.Selection([
        ('whole_subscription', 'Whole Subscription'),
        ('specific_products', 'Specific Products'),
    ], string='Application Scope', default='whole_subscription', required=True,
       help='Apply discount across entire subscription or restrict to designated product lines.')

    product_ids = fields.Many2many(
        'product.product',
        string='Eligible Products',
        domain="['|', ('is_subscription', '=', True), ('product_tmpl_id.is_subscription', '=', True)]",
        help='When scope is set to Specific Products, only these lines receive the discount.'
    )

    # Eligibility Thresholds
    min_quantity = fields.Float(
        string='Minimum Quantity / Seats',
        default=0.0,
        help='Minimum seats or units required to qualify for this discount.'
    )
    min_amount = fields.Float(
        string='Minimum Purchase Amount',
        default=0.0,
        help='Minimum untaxed spend required to qualify for this discount.'
    )
    start_date = fields.Date(
        string='Valid From',
        help='Earliest date on which this discount can be applied.'
    )
    end_date = fields.Date(
        string='Valid Until',
        help='Latest date on which this discount can be applied.'
    )

    # Usage Limits
    max_usage_limit = fields.Integer(
        string='Usage Limit',
        default=0,
        help='Maximum number of invoices that can redeem this discount. 0 means unlimited.'
    )
    current_usage_count = fields.Integer(
        string='Times Used',
        default=0,
        readonly=True,
        copy=False,
        help='Number of invoices that have redeemed this discount rule.'
    )

    description = fields.Text(
        string='Terms & Conditions',
        translate=True
    )

    @api.constrains('discount_value', 'discount_type')
    def _check_discount_value(self):
        for rule in self:
            if rule.discount_value <= 0:
                raise ValidationError(_('Discount value must be strictly greater than zero.'))
            if rule.discount_type == 'percentage' and rule.discount_value > 100.0:
                raise ValidationError(_('Percentage discount cannot exceed 100%.'))

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rule in self:
            if rule.start_date and rule.end_date and rule.end_date < rule.start_date:
                raise ValidationError(_(
                    'Discount rule "%s": Valid Until (%s) cannot be earlier than Valid From (%s).'
                ) % (rule.name, rule.end_date, rule.start_date))

    @api.constrains('min_quantity', 'min_amount', 'max_usage_limit')
    def _check_thresholds(self):
        for rule in self:
            if rule.min_quantity < 0:
                raise ValidationError(_('Minimum quantity cannot be negative.'))
            if rule.min_amount < 0:
                raise ValidationError(_('Minimum amount cannot be negative.'))
            if rule.max_usage_limit < 0:
                raise ValidationError(_('Maximum usage limit cannot be negative.'))

    @api.model_create_multi
    def create(self, vals_list):
        if not (self.env.user.has_group('brightloop_subscription.group_subscription_manager') or self.env.is_superuser()):
            raise AccessError(_('Access Denied: Only a Subscription Administrator can create discount rules.'))
        return super().create(vals_list)

    def write(self, vals):
        # Allow internal system updating current_usage_count
        if set(vals.keys()) == {'current_usage_count'}:
            return super().write(vals)
        if not (self.env.user.has_group('brightloop_subscription.group_subscription_manager') or self.env.is_superuser()):
            raise AccessError(_('Access Denied: Only a Subscription Administrator can modify discount rules.'))
        return super().write(vals)

    def unlink(self):
        if not (self.env.user.has_group('brightloop_subscription.group_subscription_manager') or self.env.is_superuser()):
            raise AccessError(_('Access Denied: Only a Subscription Administrator can delete discount rules.'))
        return super().unlink()

    def is_eligible(self, subscription, evaluation_date=None):
        """Verifies if the discount rule is valid and applicable for the subscription on given date."""
        self.ensure_one()
        if not self.active:
            return False

        eval_date = evaluation_date or fields.Date.context_today(self)
        if self.start_date and eval_date < self.start_date:
            return False
        if self.end_date and eval_date > self.end_date:
            return False

        # Usage limit check
        if self.max_usage_limit > 0 and self.current_usage_count >= self.max_usage_limit:
            return False

        # Scope and threshold evaluation
        if self.scope == 'specific_products':
            matching_lines = subscription.line_ids.filtered(lambda l: l.product_id in self.product_ids)
            if not matching_lines:
                return False
            qty = sum(l.quantity for l in matching_lines)
            amt = sum(l.price_subtotal for l in matching_lines)
        else:
            qty = subscription.total_quantity
            amt = subscription.amount_untaxed

        if self.min_quantity > 0 and qty < self.min_quantity:
            return False
        if self.min_amount > 0 and amt < self.min_amount:
            return False

        return True

    def compute_discount_amount(self, subscription):
        """Calculates the currency discount amount applicable to the subscription."""
        self.ensure_one()
        if self.scope == 'specific_products':
            matching_lines = subscription.line_ids.filtered(lambda l: l.product_id in self.product_ids)
            base_amount = sum(l.price_subtotal for l in matching_lines)
        else:
            base_amount = subscription.amount_untaxed

        if self.discount_type == 'percentage':
            discount = (base_amount * self.discount_value) / 100.0
        else:
            discount = min(self.discount_value, base_amount)

        return round(discount, 2)
