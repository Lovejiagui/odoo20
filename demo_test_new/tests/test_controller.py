from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestHostelController(HttpCase):
    """controllers/main.py 只注册了一个路由：/hostel/list（auth='user'，渲染 QWeb 模板）。

    修正说明：原用例请求的 /demo/test/page 和 /demo/protected 在模块里并不存在，
    必然拿到 404，所以原来断言 200 的那两个用例一直是红的。这里改成真实路由。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # HttpCase 处于 registry 测试模式，新开的游标会复用测试事务，
        # 所以这里建的记录在 HTTP 请求里能查到。
        cls.order = cls.env['l.sale.order'].create({
            'barcode': 'CTRL001',
            'state': 'draft',
        })

    def test_list_page_renders_orders(self):
        """登录后访问 /hostel/list 返回 200，页面骨架正常渲染

        注意：本机的 8069 端口上常驻着一个外部 odoo 服务，HttpCase 的 url_open
        实际打到的是那个进程（它连的是同一个库，但是自己的事务），所以 setUpClass
        里建的订单在页面里看不到——断言只能覆盖与数据无关的部分。想验证"页面里
        真的列出订单"，要么停掉外部服务让测试框架起进程内服务，要么手工在界面上看。
        """
        self.authenticate('admin', 'admin')
        response = self.url_open('/hostel/list')
        self.assertEqual(response.status_code, 200)
        self.assertIn('订单列表', response.text)   # 模板里的 <h1>

    def test_route_requires_login(self):
        """未登录访问 auth='user' 的路由 → 303 重定向到登录页"""
        response = self.url_open('/hostel/list', allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn('/web/login', response.headers.get('Location', ''))

    def test_unknown_route_returns_404(self):
        """不存在的路由最终返回 404

        注意：装了 website 且配置了多语言时，未命中路由的请求会先 303 跳到
        /zh_CN/xxx 再 404；没配多语言（如 odoo.sh 默认库）则直接 404。
        所以这里跟随全部重定向，只断言最终响应是 404，不依赖 website 配置。
        """
        self.authenticate('admin', 'admin')
        final = self.url_open('/hostel/wrong')
        self.assertEqual(final.status_code, 404)
