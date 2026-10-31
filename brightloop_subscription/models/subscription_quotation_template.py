# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SubscriptionQuotationTemplate(models.Model):
    _name = 'subscription.quotation.template'
    _description = 'Subscription Quotation Template'
    _order = 'name, id'

    name = fields.Char(
        string='Template Name',
        required=True,
        translate=True,
        help='Display name of the quotation template (e.g. Standard SaaS Offer, Enterprise Annual Bundle).'
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
    plan_id = fields.Many2one(
        'subscription.plan',
        string='Default Plan',
        required=True,
        help='The subscription plan automatically selected when this template is used.'
    )
    validity_days = fields.Integer(
        string='Quotation Validity (Days)',
        default=30,
        required=True,
        help='Number of days from quotation creation before the offer expires.'
    )
    line_ids = fields.One2many(
        'subscription.quotation.template.line',
        'template_id',
        string='Pre-configured Product Lines',
        copy=True
    )
    description = fields.Text(
        string='Terms & Conditions',
        translate=True,
        help='Terms and notes displayed on the quotation document.'
    )

    @api.constrains('validity_days')
    def _check_validity_days(self):
        for template in self:
            if template.validity_days <= 0:
                raise ValidationError(_(
                    'Quotation validity days must be a positive integer greater than zero (found %s).'
                ) % template.validity_days)


class SubscriptionQuotationTemplateLine(models.Model):
    _name = 'subscription.quotation.template.line'
    _description = 'Subscription Quotation Template Line'
    _order = 'id'

    template_id = fields.Many2one(
        'subscription.quotation.template',
        string='Template',
        required=True,
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        help='Subscription product variant included in this template line.'
    )
    name = fields.Text(
        string='Description',
        help='Line description shown to the customer.'
    )
    quantity = fields.Float(
        string='Default Quantity',
        default=1.0,
        required=True
    )
    price_unit = fields.Float(
        string='Unit Price',
        digits='Product Price',
        help='Preset unit price override. Leave at 0.0 to automatically use the product variant price.'
    )

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.display_name
            if not self.price_unit:
                self.price_unit = self.product_id.lst_price

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_(
                    'Template line quantity must be greater than zero.'
                ))
