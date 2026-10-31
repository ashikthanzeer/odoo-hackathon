# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SubscriptionBillingWizard(models.TransientModel):
    _name = 'subscription.billing.wizard'
    _description = 'Batch Subscription Billing Wizard'

    billing_date = fields.Date(
        string='Billing Target Date',
        default=fields.Date.context_today,
        required=True,
        help='Invoices will be generated for all active subscriptions due on or before this date.'
    )
    due_subscription_ids = fields.Many2many(
        'subscription.subscription',
        string='Subscriptions Due for Billing',
        compute='_compute_due_subscriptions',
        readonly=False
    )
    due_count = fields.Integer(
        string='Subscriptions Due',
        compute='_compute_due_subscriptions'
    )

    @api.depends('billing_date')
    def _compute_due_subscriptions(self):
        for wizard in self:
            target = wizard.billing_date or fields.Date.context_today(wizard)
            subs = self.env['subscription.subscription'].search([
                ('state', '=', 'active'),
                ('next_billing_date', '<=', target)
            ])
            wizard.due_subscription_ids = subs
            wizard.due_count = len(subs)

    def action_process_billing(self):
        """Processes recurring invoices for all due subscriptions."""
        self.ensure_one()
        subs_to_bill = self.due_subscription_ids
        if not subs_to_bill:
            raise UserError(_('No active subscriptions are due for billing on or before %s.') % self.billing_date)

        generated_invoices = self.env['account.move']
        errors = []
        for sub in subs_to_bill:
            try:
                inv = sub.action_generate_invoice(target_date=self.billing_date)
                generated_invoices |= inv
            except Exception as e:
                errors.append(f"{sub.name}: {str(e)}")

        action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_out_invoice_type')
        action['domain'] = [('id', 'in', generated_invoices.ids)]
        action['context'] = {'default_move_type': 'out_invoice'}

        if errors:
            action['help'] = _(
                "<p class='text-danger'>Generated %d invoices with %d error(s):</p><p>%s</p>"
            ) % (len(generated_invoices), len(errors), "<br/>".join(errors))

        return action
