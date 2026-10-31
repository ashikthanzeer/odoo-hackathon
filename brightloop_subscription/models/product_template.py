# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_subscription = fields.Boolean(
        string='Subscription Product',
        default=False,
        help='Check this box if the product is offered as a recurring subscription service or license.'
    )
    subscription_plan_id = fields.Many2one(
        'subscription.plan',
        string='Default Subscription Plan',
        help='Default billing cycle plan associated with this subscription product.'
    )
    subscription_notes = fields.Text(
        string='Subscription Terms & Notes',
        translate=True,
        help='Terms, service levels, or details specific to recurring subscriptions of this product.'
    )

    def action_view_variants_with_pricing(self):
        """Helper action to inspect variant pricing surcharges."""
        self.ensure_one()
        return {
            'name': _('Product Variants & Pricing'),
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'view_mode': 'list,form',
            'domain': [('product_tmpl_id', '=', self.id)],
            'context': {'default_product_tmpl_id': self.id},
        }


class ProductProduct(models.Model):
    _inherit = 'product.product'

    subscription_effective_price = fields.Float(
        string='Effective Subscription Price',
        compute='_compute_subscription_effective_price',
        help='Base template list price plus variant attribute value extra surcharges.'
    )

    @api.depends('lst_price', 'product_template_attribute_value_ids.price_extra')
    def _compute_subscription_effective_price(self):
        for product in self:
            product.subscription_effective_price = product.lst_price
