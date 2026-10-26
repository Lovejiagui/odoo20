from odoo import http
from odoo.http import request

class HostelController(http.Controller):
    @http.route('/hostel/list', type='http', auth='user')
    def hostel_list(self, **kw):
        # 去掉 sudo()，让当前登录用户的 ACL + 记录规则自然生效：
        # 没加组的用户会直接拿到 AccessError，操作员看不到规则之外的记录。
        orders = request.env['l.sale.order'].search([])
        return request.render("demo_test_new.l_sale_order", {
            'orders': orders
        })
