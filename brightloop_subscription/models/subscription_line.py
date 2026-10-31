# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SubscriptionLine(models.Model):
    _name = 'subscription.line'
    _description = 'Subscription Line'
    _order = 'id'

    subscription_id = fields.Many2one(
        'subscription.subscription',
        string='Subscription',
        required=True,
        ondelete='cascade',
        index=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain="['|', ('is_subscription', '=', True), ('product_tmpl_id.is_subscription', '=', True)]",
        help='Subscription software or service variant.'
    )
    name = fields.Text(
        string='Description',
        required=True,
        help='Line description shown on quote and invoice.'
    )
    quantity = fields.Float(
        string='Quantity',
        default=1.0,
        required=True
    )
    price_unit = fields.Float(
        string='Unit Price',
        digits='Product Price',
        required=True,
        default=0.0
    )
    tax_ids = fields.Many2many(
        'account.tax',
        string='Taxes',
        domain="[('type_tax_use', '=', 'sale')]"
    )
    currency_id = fields.Many2one(
        related='subscription_id.currency_id',
        string='Currency',
        store=True,
        readonly=True
    )
    price_subtotal = fields.Monetary(
        string='Subtotal',
        compute='_compute_amount',
        store=True,
        currency_field='currency_id'
    )
    price_tax = fields.Monetary(
        string='Tax Amount',
        compute='_compute_amount',
        store=True,
        currency_field='currency_id'
    )
    price_total = fields.Monetary(
        string='Total Amount',
        compute='_compute_amount',
        store=True,
        currency_field='currency_id'
    )

    @api.depends('quantity', 'price_unit', 'tax_ids', 'currency_id')
    def _compute_amount(self):
        for line in self:
            price = line.price_unit
            taxes = line.tax_ids.compute_all(
                price,
                line.currency_id,
                line.quantity,
                product=line.product_id,
                partner=line.subscription_id.partner_id
            )
            line.update({
                'price_subtotal': taxes['total_excluded'],
                'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                'price_total': taxes['total_included'],
            })

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.get_product_multiline_description_sale() if hasattr(self.product_id, 'get_product_multiline_description_sale') else self.product_id.display_name
            self.price_unit = self.product_id.lst_price
            if self.product_id.taxes_id:
                self.tax_ids = self.product_id.taxes_id

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_(
                    'Line quantity must be strictly greater than zero.'
                ))
