from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSaleOrderLine(TransactionCase):
    """l.sale.order.line：字段精度与 button_add 的税项处理

    button_add 现在按税率（TARGET_TAX_AMOUNT = 21.0）动态解析税项——先查后用，
    所以可以反复点，也不会跟账套里已有的同号税项撞名。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Line = cls.env['l.sale.order.line']
        cls.order = cls.env['l.sale.order'].create({'barcode': 'LINE-001'})
        cls.line = cls.Line.create({'order_id': cls.order.id, 'name': '明细1'})

    def _taxes_21_percent(self):
        """当前账套里 21% 的销售税"""
        return self.env['account.tax'].search([
            ('amount', '=', 21.0),
            ('type_tax_use', '=', 'sale'),
        ])

    def _move_away_21_percent_taxes(self):
        """把已有的 21% 销售税挪开（amount 和 name 一起改），模拟"还没建过这条税"。

        改名必须各自唯一，否则会撞上 account.tax 的税名唯一约束。
        测试跑在事务里，结束会回滚，不影响真实数据。
        """
        taxes = self._taxes_21_percent()
        for index, tax in enumerate(taxes):
            tax.write({'name': f'被测试挪开的税-{index}', 'amount': 0.5})
        self.env.flush_all()
        return taxes

    # ---------------- 关联与字段 ----------------

    def test_line_linked_to_order(self):
        self.assertEqual(self.line.order_id, self.order)
        self.assertIn(self.line, self.order.line_ids)

    def test_tax_ids_is_empty_by_default(self):
        self.assertFalse(self.line.tax_ids)

    def test_amount_total_keeps_three_decimals(self):
        """amount_total 的 digits=(16, 3)，多的位会被截掉"""
        self.line.amount_total = 10.1234
        self.line.flush_recordset()
        self.line.invalidate_recordset()
        self.assertAlmostEqual(self.line.amount_total, 10.123, places=3)

    def test_price_unit_and_qty_are_writable(self):
        self.line.write({'price_unit': 12.5, 'qty': 3.0})
        self.assertAlmostEqual(self.line.price_unit, 12.5)
        self.assertAlmostEqual(self.line.qty, 3.0)

    # ---------------- button_add ----------------

    def test_button_add_reuses_existing_tax(self):
        """账套里已有 21% 销售税 → 直接复用，不新建

        不依赖账套预置数据：先把已有 21% 税挪开，再自己造一条"已存在的"21% 税，
        验证 button_add 走的是复用分支（这正是改之前会崩的场景：原来硬编码
        name='21%' 去新建，撞上已有税项就抛 ValidationError: Tax names must be unique!）
        """
        self._move_away_21_percent_taxes()
        self.assertFalse(self._taxes_21_percent())
        existing = self.env['account.tax'].create({
            'name': '测试预置21%税',
            'amount': 21.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'company_id': self.env.company.id,
        })

        before = self.env['account.tax'].search_count([])
        self.line.button_add()

        self.assertEqual(self.env['account.tax'].search_count([]), before)  # 没有新增税项
        self.assertEqual(len(self.line.tax_ids), 1)
        self.assertEqual(self.line.tax_ids, existing)
        self.assertAlmostEqual(self.line.tax_ids.amount, 21.0)

    def test_button_add_is_idempotent(self):
        """反复点结果一致，不会像原来那样越点越多

        以第一次点击之后的状态为基准（此时 21% 税必定已存在，后续点击走复用分支），
        再点两次断言：行上税项不变、库里税项总数不再增长。
        这样无论账套里原本有没有 21% 税都成立。
        """
        self.line.button_add()
        first_ids = self.line.tax_ids.ids
        self.assertTrue(first_ids, '第一次点击后行上应有税项')
        count_after_first = self.env['account.tax'].search_count([])

        self.line.button_add()
        self.line.button_add()

        self.assertEqual(self.line.tax_ids.ids, first_ids)
        self.assertEqual(len(self.line.tax_ids), 1)
        self.assertEqual(self.env['account.tax'].search_count([]), count_after_first)

    def test_button_add_creates_tax_when_missing(self):
        """账套里确实没有这条税时才新建，名称按税率动态拼出来"""
        self._move_away_21_percent_taxes()
        self.assertFalse(self._taxes_21_percent())

        before = self.env['account.tax'].search_count([])
        self.line.button_add()

        self.assertEqual(self.env['account.tax'].search_count([]) - before, 1)
        self.assertEqual(len(self.line.tax_ids), 1)
        self.assertAlmostEqual(self.line.tax_ids.amount, 21.0)
        self.assertEqual(self.line.tax_ids.name, '21%')
        self.assertEqual(self.line.tax_ids.type_tax_use, 'sale')

    def test_button_add_replaces_previous_taxes(self):
        """原有的税项会被整体替换掉（Command.set 语义），不是追加"""
        tax_15 = self.env['account.tax'].search([
            ('amount', '=', 15.0),
            ('type_tax_use', '=', 'sale'),
        ], limit=1)
        self.assertTrue(tax_15, '前置条件：账套里应有 15% 的销售税')
        self.line.write({'tax_ids': [Command.set(tax_15.ids)]})
        self.assertEqual(len(self.line.tax_ids), 1)

        self.line.button_add()

        self.assertEqual(len(self.line.tax_ids), 1)
        self.assertAlmostEqual(self.line.tax_ids.amount, 21.0)
