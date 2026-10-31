# -*- coding: utf-8 -*-
{
    'name': 'Brightloop Subscription Management',
    'version': '17.0.1.0.0',
    'category': 'Sales/Subscriptions',
    'summary': 'Manage plans, subscriptions, variants, and recurring billing for Brightloop Software',
    'author': 'Brightloop Software / Hackathon Team',
    'website': 'https://brightloop.example.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'product',
        'mail',
        'portal',
    ],
    'data': [
        'security/subscription_security.xml',
        'security/ir.model.access.csv',
        'views/subscription_menus.xml',
        'views/subscription_plan_views.xml',
        'views/product_views.xml',
        'views/res_partner_views.xml',
    ],
    'demo': [
        'demo/subscription_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
