{
    'name': 'Test new',
    'version': '1.0',
    'summary': '我的新测试模块',
    'description': '测试模块的详细描述',
    'category': '',
    'depends': ['base','product','account','mail','website','web', 'sale'],
    'data': [
        'security/groups.xml',
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/l_sale_order_views.xml',
        'views/l_task_views.xml',
        'views/res_users_views.xml',
        'views/menu_views.xml',
        'wizard/l_sale_order_wizard.xml',
        'views/web_l_sale_order.xml',


    ],
'assets': {
    'web.assets_backend': [
        'demo_test_new/static/src/xml/carousel_template.xml',
        'demo_test_new/static/src/js/carousel_widget.js',
        'demo_test_new/static/src/scss/carousel.scss',
    ],
},
    'installable': True,
    'application': True,
    'author': 'Lee',
    'license': 'LGPL-3',
}
