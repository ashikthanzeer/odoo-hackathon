# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    subscription_id = fields.Many2one(
        'subscription.subscription',
        string='Subscription',
        index=True,
        copy=False,
        help='The subscription contract from which this recurring invoice was generated.'
    )
