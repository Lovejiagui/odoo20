from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSaleOrderWizard(TransactionCase):
    """l.sale.order.wizard：列表勾选单据后的批量处理向导"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.order_a = cls.env['l.sale.order'].create({
            'barcode': 'WZ-A',
            'note': '原始备注A',
            'payment_type': 'v_1',
        })
        cls.order_b = cls.env['l.sale.order'].create({
            'barcode': 'WZ-B',
            'note': '原始备注B',
            'payment_type': 'v_1',
        })

    def _wizard(self, orders, **vals):
        """模拟列表勾选后打开向导：靠 context.active_ids 带出单据"""
        return self.env['l.sale.order.wizard'].with_context(
            active_ids=orders.ids,
            active_model='l.sale.order',
        ).create(vals)

    # ---------------- 带出勾选的单据 ----------------

    def test_order_ids_default_from_active_ids(self):
        wizard = self._wizard(self.order_a | self.order_b)
        self.assertEqual(
            sorted(wizard.order_ids.ids),
            sorted((self.order_a | self.order_b).ids),
        )
        self.assertEqual(wizard.order_count, 2)

    def test_order_count_is_zero_without_selection(self):
        wizard = self.env['l.sale.order.wizard'].with_context(active_ids=[]).create({})
        self.assertFalse(wizard.order_ids)
        self.assertEqual(wizard.order_count, 0)

    # ---------------- action_confirm ----------------

    def test_confirm_writes_payment_type_and_closes(self):
        wizard = self._wizard(self.order_a, payment_type='v_2')
        result = wizard.action_confirm()
        self.assertEqual(self.order_a.payment_type, 'v_2')
        self.assertEqual(result, {'type': 'ir.actions.act_window_close'})

    def test_confirm_leaves_empty_fields_untouched(self):
        """留空的字段不会被改写"""
        original_date = self.order_a.validate_date
        wizard = self._wizard(self.order_a, payment_type='v_3')
        wizard.action_confirm()
        self.assertEqual(self.order_a.payment_type, 'v_3')
        self.assertEqual(self.order_a.validate_date, original_date)
        self.assertIn('原始备注A', self.order_a.note)

    def test_confirm_writes_all_three_fields(self):
        """三个字段都填了就都写回；remark 落到 note 上（Html 字段会自动包 <p>）"""
        new_date = date(2030, 1, 1)
        wizard = self._wizard(
            self.order_a,
            payment_type='v_2',
            validate_date=new_date,
            remark='批量备注',
        )
        wizard.action_confirm()
        self.assertEqual(self.order_a.payment_type, 'v_2')
        self.assertEqual(self.order_a.validate_date, new_date)
        self.assertIn('批量备注', self.order_a.note)

    def test_confirm_applies_to_all_selected_orders(self):
        """勾选多条时全部写回"""
        orders = self.order_a | self.order_b
        wizard = self._wizard(orders, payment_type='v_3')
        wizard.action_confirm()
        self.assertEqual(set(orders.mapped('payment_type')), {'v_3'})

    def test_confirm_does_not_touch_state(self):
        """批量处理只改付款条款/有效期/备注，不动订单状态"""
        wizard = self._wizard(self.order_a, payment_type='v_2')
        wizard.action_confirm()
        self.assertEqual(self.order_a.state, 'draft')

    def test_confirm_without_selection_raises(self):
        """没勾选单据就提交 → UserError"""
        wizard = self.env['l.sale.order.wizard'].with_context(
            active_ids=[],
        ).create({'payment_type': 'v_1'})
        with self.assertRaises(UserError):
            wizard.action_confirm()

    def test_confirm_with_empty_form_raises(self):
        """勾选了单据但一个字段都没填 → UserError"""
        wizard = self._wizard(self.order_a)
        with self.assertRaises(UserError):
            wizard.action_confirm()
