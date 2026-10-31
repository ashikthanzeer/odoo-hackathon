# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_subscription_customer = fields.Boolean(
        string='Subscription Customer',
        default=False,
        help='Indicates whether this partner is an active or registered subscription customer.'
    )
    subscription_count = fields.Integer(
        string='Subscription Count',
        compute='_compute_subscription_count',
        help='Total number of subscriptions associated with this partner.'
    )
    subscription_notes = fields.Text(
        string='Subscription Notes',
        help='Specific onboarding or billing instructions for this customer.'
    )

    def _compute_subscription_count(self):
        # Stub to be expanded when subscription model is introduced in downstream change
        for partner in self:
            partner.subscription_count = 0

    @api.constrains('email')
    def _check_unique_customer_email(self):
        for partner in self:
            if partner.email and partner.is_subscription_customer:
                normalized_email = partner.email.strip().lower()
                duplicate = self.search([
                    ('id', '!=', partner.id),
                    ('email', '=ilike', normalized_email),
                    ('is_subscription_customer', '=', True)
                ], limit=1)
                if duplicate:
                    raise ValidationError(_(
                        'A subscription customer with email address "%s" already exists in the system (Partner: %s). Each customer account email must be unique.'
                    ) % (partner.email, duplicate.display_name))
