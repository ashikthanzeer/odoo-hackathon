# -*- coding: utf-8 -*-
import logging
from datetime import date
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class Subscription(models.Model):
    _name = 'subscription.subscription'
    _description = 'Brightloop Subscription Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Subscription Number',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default='New',
        tracking=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        tracking=True,
        index=True,
        domain="[('is_company', '=', True), '|', ('parent_id', '=', False), ('is_company', '=', False)]"
    )
    plan_id = fields.Many2one(
        'subscription.plan',
        string='Subscription Plan',
        required=True,
        tracking=True,
        index=True
    )
    template_id = fields.Many2one(
        'subscription.quotation.template',
        string='Quotation Template',
        help='Applying a template pre-fills default plan, product lines, and expiry validity.'
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
        related='plan_id.currency_id',
        store=True,
        readonly=True
    )
    payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Payment Terms'
    )
    start_date = fields.Date(
        string='Start Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True
    )
    expiry_date = fields.Date(
        string='Expiry Date',
        tracking=True,
        help='Date when this contract term expires or quote validity terminates.'
    )
    next_billing_date = fields.Date(
        string='Next Billing Date',
        copy=False,
        index=True,
        tracking=True,
        help='Date on which the next recurring invoice is due to be generated.'
    )
    last_billing_date = fields.Date(
        string='Last Invoiced Date',
        readonly=True,
        copy=False,
        help='Date of the most recent billing cycle invoice.'
    )
    user_id = fields.Many2one(
        'res.users',
        string='Salesperson',
        default=lambda self: self.env.user,
        tracking=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('quotation', 'Quotation'),
        ('confirmed', 'Confirmed'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('closed', 'Closed'),
    ], string='Status', default='draft', required=True, tracking=True, index=True)

    line_ids = fields.One2many(
        'subscription.line',
        'subscription_id',
        string='Subscription Lines',
        copy=True
    )
    total_quantity = fields.Float(
        string='Total Quantity',
        compute='_compute_amounts',
        store=True
    )
    discount_rule_id = fields.Many2one(
        'subscription.discount.rule',
        string='Discount Rule',
        domain="[('active', '=', True)]",
        tracking=True,
        help='Promotional or volume discount rule applied to this contract.'
    )
    discount_amount = fields.Monetary(
        string='Discount Amount',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    amount_untaxed = fields.Monetary(
        string='Untaxed Amount',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
        tracking=True
    )
    amount_tax = fields.Monetary(
        string='Taxes',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    amount_total = fields.Monetary(
        string='Total Amount',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
        tracking=True
    )
    amount_net = fields.Monetary(
        string='Net Total',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
        tracking=True
    )
    mrr = fields.Monetary(
        string='Monthly Recurring Revenue',
        compute='_compute_recurring_revenue',
        store=True,
        currency_field='currency_id',
        tracking=True,
        help='Normalized recurring revenue earned per month.'
    )
    arr = fields.Monetary(
        string='Annual Recurring Revenue',
        compute='_compute_recurring_revenue',
        store=True,
        currency_field='currency_id',
        tracking=True,
        help='Normalized recurring revenue earned per year.'
    )
    notes = fields.Html(
        string='Terms and Conditions'
    )

    # Invoicing linkage
    invoice_ids = fields.One2many(
        'account.move',
        'subscription_id',
        string='Invoices',
        readonly=True
    )
    invoice_count = fields.Integer(
        string='Invoices Count',
        compute='_compute_invoice_count'
    )
    payment_status = fields.Selection([
        ('draft', 'Draft / No Invoices'),
        ('pending', 'Pending Payment'),
        ('partial', 'Partially Paid'),
        ('paid', 'Fully Paid'),
        ('overdue', 'Overdue'),
    ], string='Payment Status', compute='_compute_payment_metrics', store=True, tracking=True, default='draft', index=True)

    paid_amount = fields.Monetary(
        string='Paid Amount',
        compute='_compute_payment_metrics',
        store=True,
        currency_field='currency_id',
        tracking=True
    )
    amount_due = fields.Monetary(
        string='Balance Due',
        compute='_compute_payment_metrics',
        store=True,
        currency_field='currency_id',
        tracking=True
    )
    payment_count = fields.Integer(
        string='Payments Count',
        compute='_compute_payment_count'
    )

    def _compute_invoice_count(self):
        for sub in self:
            sub.invoice_count = len(sub.invoice_ids)

    def _get_reconciled_payments(self):
        """Helper to collect all account.payment records reconciled against the subscription's invoices."""
        self.ensure_one()
        payments = self.env['account.payment']
        for inv in self.invoice_ids:
            if hasattr(inv, '_get_reconciled_payments'):
                try:
                    payments |= inv._get_reconciled_payments()
                except Exception:
                    pass
            if hasattr(inv, 'payment_ids') and inv.payment_ids:
                payments |= inv.payment_ids
        return payments

    def _compute_payment_count(self):
        for sub in self:
            sub.payment_count = len(sub._get_reconciled_payments())

    @api.depends(
        'invoice_ids.state',
        'invoice_ids.payment_state',
        'invoice_ids.amount_residual',
        'invoice_ids.amount_total',
        'invoice_ids.invoice_date_due'
    )
    def _compute_payment_metrics(self):
        for sub in self:
            posted_invoices = sub.invoice_ids.filtered(lambda inv: inv.state == 'posted')
            if not posted_invoices:
                sub.update({
                    'paid_amount': 0.0,
                    'amount_due': 0.0,
                    'payment_status': 'draft',
                })
                continue

            paid_amt = sum(inv.amount_total - inv.amount_residual for inv in posted_invoices)
            due_amt = sum(inv.amount_residual for inv in posted_invoices)
            today = fields.Date.context_today(sub)

            has_overdue = any(
                inv.amount_residual > 0 and inv.invoice_date_due and inv.invoice_date_due < today
                for inv in posted_invoices
            )

            if has_overdue:
                status = 'overdue'
            elif all(inv.payment_state in ('paid', 'in_payment') or inv.amount_residual == 0 for inv in posted_invoices):
                status = 'paid'
            elif any(inv.payment_state == 'partial' for inv in posted_invoices) or (paid_amt > 0 and due_amt > 0):
                status = 'partial'
            else:
                status = 'pending'

            sub.update({
                'paid_amount': max(0.0, paid_amt),
                'amount_due': max(0.0, due_amt),
                'payment_status': status,
            })

    @api.depends('line_ids.price_subtotal', 'line_ids.price_tax', 'line_ids.price_total', 'line_ids.quantity', 'discount_rule_id', 'discount_rule_id.discount_type', 'discount_rule_id.discount_value', 'discount_rule_id.active')
    def _compute_amounts(self):
        for sub in self:
            amount_untaxed = sum(line.price_subtotal for line in sub.line_ids)
            amount_tax = sum(line.price_tax for line in sub.line_ids)
            amount_total = sum(line.price_total for line in sub.line_ids)
            total_qty = sum(line.quantity for line in sub.line_ids)

            discount_amount = 0.0
            eval_date = sub.start_date or fields.Date.context_today(sub)
            if sub.discount_rule_id and sub.discount_rule_id.is_eligible(sub, evaluation_date=eval_date):
                discount_amount = sub.discount_rule_id.compute_discount_amount(sub)

            amount_net = max(0.0, amount_total - discount_amount)
            sub.update({
                'amount_untaxed': amount_untaxed,
                'amount_tax': amount_tax,
                'amount_total': amount_total,
                'discount_amount': discount_amount,
                'amount_net': amount_net,
                'total_quantity': total_qty,
            })

    @api.depends('amount_net', 'plan_id.billing_cycle_unit', 'plan_id.billing_interval')
    def _compute_recurring_revenue(self):
        for sub in self:
            interval = sub.plan_id.billing_interval or 1
            unit = sub.plan_id.billing_cycle_unit or 'monthly'
            amount = sub.amount_net or 0.0

            if unit == 'monthly':
                mrr = amount / interval
                arr = mrr * 12.0
            elif unit == 'yearly':
                mrr = amount / (12.0 * interval)
                arr = amount / interval
            elif unit == 'weekly':
                mrr = (amount * 52.0) / (12.0 * interval)
                arr = (amount * 52.0) / interval
            elif unit == 'daily':
                mrr = (amount * 30.0) / interval
                arr = (amount * 365.0) / interval
            else:
                mrr = amount
                arr = amount * 12.0

            sub.update({
                'mrr': round(mrr, 2),
                'arr': round(arr, 2),
            })

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.template_id:
            self.plan_id = self.template_id.plan_id
            base_date = self.start_date or fields.Date.context_today(self)
            self.expiry_date = base_date + relativedelta(days=self.template_id.validity_days)
            
            lines = []
            for t_line in self.template_id.line_ids:
                lines.append((0, 0, {
                    'product_id': t_line.product_id.id,
                    'name': t_line.name or t_line.product_id.display_name,
                    'quantity': t_line.quantity,
                    'price_unit': t_line.price_unit or t_line.product_id.lst_price,
                    'tax_ids': [(6, 0, t_line.product_id.taxes_id.ids)] if t_line.product_id.taxes_id else False,
                }))
            self.line_ids = lines

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            if not self.partner_id.is_subscription_customer:
                self.partner_id.is_subscription_customer = True
            if self.partner_id.property_payment_term_id:
                self.payment_term_id = self.partner_id.property_payment_term_id

    def action_quote(self):
        """Move from draft to quotation stage."""
        for sub in self:
            if not sub.line_ids:
                raise UserError(_('Please add at least one subscription product line before sending a quote.'))
            sub.write({'state': 'quotation'})

    def action_confirm(self):
        """Confirm quotation, assign sequence number, validate constraints, and activate."""
        for sub in self:
            if not sub.line_ids:
                raise UserError(_('Cannot confirm a subscription without line items.'))

            # 1. Check plan validity on start date
            if not sub.plan_id.is_valid_on_date(sub.start_date):
                raise ValidationError(_(
                    'Plan "%s" is not valid on the start date (%s). Please select an active plan within its valid date range.'
                ) % (sub.plan_id.name, sub.start_date))

            # 2. Check plan minimum quantity
            sub.plan_id.validate_quantity(sub.total_quantity)

            # 3. Assign sequence number if still 'New'
            vals = {}
            if sub.name == 'New':
                seq = self.env['ir.sequence'].next_by_code('subscription.subscription') or 'SUB/2026/00001'
                vals['name'] = seq

            # 4. Set initial next_billing_date if not set
            if not sub.next_billing_date:
                vals['next_billing_date'] = sub.start_date

            # 5. Determine state: active if start_date <= today, else confirmed
            today = fields.Date.context_today(sub)
            if sub.start_date <= today:
                vals['state'] = 'active'
            else:
                vals['state'] = 'confirmed'

            sub.write(vals)

    def action_activate(self):
        """Manually transition confirmed subscription to active."""
        for sub in self:
            if sub.state != 'confirmed':
                raise UserError(_('Only confirmed subscriptions can be activated.'))
            vals = {'state': 'active'}
            if not sub.next_billing_date:
                vals['next_billing_date'] = sub.start_date
            sub.write(vals)

    def action_pause(self):
        """Pause an active subscription if plan permits."""
        for sub in self:
            if sub.state != 'active':
                raise UserError(_('Only active subscriptions can be paused.'))
            if not sub.plan_id.allow_pause:
                raise ValidationError(_(
                    'Policy Restriction: Plan "%s" does not allow pausing subscriptions.'
                ) % sub.plan_id.name)
            sub.write({'state': 'paused'})

    def action_resume(self):
        """Resume a paused subscription."""
        for sub in self:
            if sub.state != 'paused':
                raise UserError(_('Only paused subscriptions can be resumed.'))
            sub.write({'state': 'active'})

    def action_close(self):
        """Close an active or paused subscription, validating early closure policy."""
        today = fields.Date.context_today(self)
        for sub in self:
            if sub.state in ('draft', 'quotation', 'closed'):
                continue
            if sub.expiry_date and today < sub.expiry_date and not sub.plan_id.allow_close_early:
                raise ValidationError(_(
                    'Policy Restriction: Plan "%s" does not allow early termination before the contract expiry date (%s).'
                ) % (sub.plan_id.name, sub.expiry_date))
            sub.write({'state': 'closed'})

    def action_draft(self):
        """Reset subscription back to draft."""
        for sub in self:
            sub.write({'state': 'draft'})

    def action_generate_invoice(self, target_date=None):
        """Generates a customer invoice for the current billing cycle with idempotency protections."""
        self.ensure_one()
        today = target_date or fields.Date.context_today(self)

        # Idempotency guard 1: Contract state
        if self.state != 'active':
            raise UserError(_(
                'Cannot generate invoice for subscription "%s": Contract is in state "%s" (must be Active).'
            ) % (self.name, self.state))

        # Idempotency guard 2: Lines present
        if not self.line_ids:
            raise UserError(_(
                'Cannot generate invoice for subscription "%s": No subscription lines found.'
            ) % self.name)

        # Idempotency guard 3: Due date check
        billing_date = self.next_billing_date or self.start_date
        if billing_date > today:
            raise UserError(_(
                'Subscription "%s" is not due for billing yet (Next billing date: %s, Evaluation date: %s).'
            ) % (self.name, billing_date, today))

        # Idempotency guard 4: Prevent duplicate invoice when draft invoice exists
        draft_invoices = self.invoice_ids.filtered(lambda inv: inv.state == 'draft')
        if draft_invoices:
            raise ValidationError(_(
                'A draft invoice ("%s") already exists for subscription "%s". Please confirm or cancel it before generating a new invoice.'
            ) % (draft_invoices[0].name or draft_invoices[0].id, self.name))

        # Construct Invoice Lines
        invoice_lines = []
        # Locate or assign sale journal
        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        income_account = False
        if journal and journal.default_account_id:
            income_account = journal.default_account_id
        if not income_account:
            income_account = self.env['account.account'].search([
                ('account_type', '=', 'income'),
                ('company_ids', 'in', self.company_id.id),
            ], limit=1)

        for line in self.line_ids:
            line_vals = {
                'product_id': line.product_id.id,
                'name': line.name or line.product_id.display_name,
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'tax_ids': [(6, 0, line.tax_ids.ids)],
            }
            line_income = (
                line.product_id.property_account_income_id or
                line.product_id.categ_id.property_account_income_categ_id or
                income_account
            )
            if line_income:
                line_vals['account_id'] = line_income.id
            invoice_lines.append((0, 0, line_vals))

        # Evaluate and apply discount rule if eligible
        discount_rule = self.discount_rule_id
        if discount_rule and discount_rule.is_eligible(self, evaluation_date=billing_date):
            disc_amt = discount_rule.compute_discount_amount(self)
            if disc_amt > 0:
                disc_name = _('Discount: %s') % discount_rule.name
                if discount_rule.code:
                    disc_name += f' ({discount_rule.code})'
                disc_vals = {
                    'name': disc_name,
                    'quantity': 1.0,
                    'price_unit': -disc_amt,
                }
                if income_account:
                    disc_vals['account_id'] = income_account.id
                invoice_lines.append((0, 0, disc_vals))
                discount_rule.sudo().write({'current_usage_count': discount_rule.current_usage_count + 1})

        # Create Customer Invoice (account.move)
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': billing_date,
            'invoice_payment_term_id': self.payment_term_id.id if self.payment_term_id else False,
            'currency_id': self.currency_id.id,
            'company_id': self.company_id.id,
            'subscription_id': self.id,
            'narration': self.notes,
            'invoice_line_ids': invoice_lines,
        }
        if journal:
            invoice_vals['journal_id'] = journal.id
        if not self.payment_term_id:
            invoice_vals['invoice_date_due'] = billing_date
        invoice = self.env['account.move'].create(invoice_vals)

        # Advance billing schedule
        next_date = self.plan_id.calculate_next_date(billing_date)
        self.write({
            'last_billing_date': billing_date,
            'next_billing_date': next_date,
        })

        return invoice

    def action_view_invoices(self):
        """Smart button action to view all customer invoices linked to this subscription."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_out_invoice_type')
        action['domain'] = [('subscription_id', '=', self.id)]
        action['context'] = {'default_move_type': 'out_invoice', 'default_subscription_id': self.id}
        if len(self.invoice_ids) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = self.invoice_ids.id
        return action

    def action_view_payments(self):
        """Smart button action to view all customer payments reconciled against this subscription's invoices."""
        self.ensure_one()
        payments = self._get_reconciled_payments()
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_account_payments')
        action['domain'] = [('id', 'in', payments.ids)]
        action['context'] = {'default_partner_id': self.partner_id.id}
        if len(payments) == 1:
            action['views'] = [(self.env.ref('account.view_account_payment_form').id, 'form')]
            action['res_id'] = payments.id
        return action

    def action_renew(self):
        """Renew the subscription contract for another cycle duration if the plan permits."""
        for sub in self:
            if not sub.plan_id.allow_renewal:
                raise ValidationError(_(
                    'Policy Restriction: Plan "%s" does not allow renewing subscriptions.'
                ) % sub.plan_id.name)
            if sub.state not in ('active', 'paused', 'closed'):
                raise UserError(_('Only active, paused, or closed subscriptions can be renewed.'))

            base_date = sub.expiry_date or fields.Date.context_today(sub)
            next_expiry = sub.plan_id.calculate_next_date(base_date)

            vals = {'expiry_date': next_expiry}
            if sub.state == 'closed':
                vals['state'] = 'active'
                if not sub.next_billing_date or sub.next_billing_date < fields.Date.context_today(sub):
                    vals['next_billing_date'] = fields.Date.context_today(sub)

            sub.write(vals)
            sub.message_post(
                body=_('Subscription successfully renewed until %s.') % next_expiry,
                message_type='notification'
            )

    @api.model
    def _cron_recurring_create_invoices(self):
        """Automated daily cron method to process all due subscriptions."""
        today = fields.Date.context_today(self)
        due_subs = self.search([
            ('state', '=', 'active'),
            ('next_billing_date', '<=', today)
        ])
        _logger.info('Recurring Billing Cron: Found %d subscriptions due for billing on %s.', len(due_subs), today)

        generated_invoices = self.env['account.move']
        for sub in due_subs:
            try:
                inv = sub.action_generate_invoice(target_date=today)
                generated_invoices |= inv
            except Exception as e:
                _logger.error('Failed to generate recurring invoice for subscription %s: %s', sub.name, e)

        _logger.info('Recurring Billing Cron: Generated %d customer invoices.', len(generated_invoices))
        return len(generated_invoices)

    @api.model
    def _cron_process_contract_expiries(self):
        """Automated daily cron method to evaluate active subscriptions reaching their expiry date."""
        today = fields.Date.context_today(self)
        expired_subs = self.search([
            ('state', '=', 'active'),
            ('expiry_date', '!=', False),
            ('expiry_date', '<=', today),
        ])
        _logger.info('Contract Expiry Cron: Found %d active subscriptions past or on expiry date as of %s.', len(expired_subs), today)

        closed_count = 0
        for sub in expired_subs:
            sub._compute_payment_metrics()
            if sub.plan_id.auto_close_on_end:
                if sub.amount_due <= 0.0 or sub.payment_status in ('paid', 'draft'):
                    sub.write({'state': 'closed'})
                    sub.message_post(
                        body=_('Subscription auto-closed upon contract expiry date (%s) with zero balance.') % sub.expiry_date,
                        message_type='notification'
                    )
                    closed_count += 1
                else:
                    sub.message_post(
                        body=_(
                            'Notice: Contract reached expiry date (%s) with an outstanding balance of %s. '
                            'Automatic closure prevented until outstanding invoices are settled.'
                        ) % (sub.expiry_date, sub.amount_due),
                        message_type='notification'
                    )

        _logger.info('Contract Expiry Cron: Closed %d expired subscriptions.', closed_count)
        return closed_count
