from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestMyModel(TransactionCase):
    """l.sale.order：单号手工录入、条码随机生成、默认值、条码查重、明细行级联删除"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.MyModel = cls.env['l.sale.order']
        # 单号手工录入；条码不用传，交给系统随机生成
        cls.test_record = cls.MyModel.create({
            'name': 'SO-TEST001',
            'state': 'draft',
            'note': '<p>测试备注</p>'
        })

    # ---------------- 创建 / 默认值 ----------------

    def test_record_create(self):
        """单号按录入的值原样保存，条码由系统自动生成"""
        self.assertEqual(self.test_record.name, 'SO-TEST001')
        self.assertTrue(self.test_record.barcode)

    def test_unsaved_record_has_no_name(self):
        """单号是手工录入的，未保存（NewId）记录没有默认单号"""
        record = self.MyModel.new({'state': 'draft'})
        self.assertFalse(record.name)

    def test_name_is_not_affected_by_state(self):
        """单号改由人工维护，改状态不会再动它"""
        self.test_record.state = 'done'
        self.assertEqual(self.test_record.name, 'SO-TEST001')

    def test_default_values(self):
        """默认值：state='draft'，validate_date=今天"""
        record = self.MyModel.create({'barcode': 'TEST010'})
        self.assertEqual(record.state, 'draft')
        self.assertEqual(record.validate_date, fields.Date.today())

    # ---------------- 条码随机生成 ----------------

    def test_barcode_is_auto_generated_and_readonly(self):
        """条码必填 + 界面只读 + 不传也能建（由 default 兜底）"""
        self.assertTrue(self.MyModel._fields['barcode'].required)
        self.assertTrue(self.MyModel._fields['barcode'].readonly)
        record = self.MyModel.create({'name': 'SO-NEW-1'})
        self.assertTrue(record.barcode)

    def test_generated_barcode_format(self):
        """自动生成的是 12 位纯数字"""
        record = self.MyModel.create({'name': 'SO-NEW-2'})
        self.assertEqual(len(record.barcode), 12)
        self.assertTrue(record.barcode.isdigit())

    def test_generated_barcodes_do_not_collide(self):
        """连建 20 张单，条码互不重复（constrains 的第二道保险）"""
        records = self.MyModel.create([{'name': f'SO-BULK-{i}'} for i in range(20)])
        barcodes = records.mapped('barcode')
        self.assertEqual(len(barcodes), 20)
        self.assertEqual(len(set(barcodes)), 20)

    def test_copy_gets_a_fresh_barcode(self):
        """复制单据不会连条码一起复制（copy=False + 重新生成）"""
        copy = self.test_record.copy()
        self.assertNotEqual(copy.barcode, self.test_record.barcode)
        self.assertTrue(copy.barcode)

    def test_explicit_barcode_is_still_respected(self):
        """手工指定条码时以指定值为准（导入旧数据时用得上）"""
        record = self.MyModel.create({'name': 'SO-NEW-3', 'barcode': 'MANUAL-001'})
        self.assertEqual(record.barcode, 'MANUAL-001')

    def test_barcode_is_required(self):
        """barcode 在 DB 上仍是 NOT NULL：显式传空会直接撞 IntegrityError"""
        self.assertTrue(self.MyModel._fields['barcode'].required)
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            self.MyModel.create({'name': 'SO-NO-BARCODE', 'barcode': False})

    def test_order_is_id_desc(self):
        """_order = 'id desc'，后创建的记录排在前面"""
        first = self.MyModel.create({'barcode': 'TEST011'})
        second = self.MyModel.create({'barcode': 'TEST012'})
        found = self.MyModel.search([('id', 'in', (first + second).ids)])
        self.assertEqual(found.ids, [second.id, first.id])
        self.assertEqual(self.MyModel._order, 'id desc')

    # ---------------- 条码查重 ----------------

    def test_barcode_unique_on_create(self):
        """用别家单子的条码创建 → ValidationError"""
        with self.assertRaises(ValidationError):
            self.MyModel.create({
                'barcode': self.test_record.barcode,
            })

    def test_barcode_conflict_with_other_record(self):
        """把 A 的条码改成 B 用过的值 → ValidationError"""
        other = self.MyModel.create({'name': 'SO-C-1'})
        with self.assertRaises(ValidationError):
            other.barcode = self.test_record.barcode

    def test_barcode_rewrite_own_value_is_allowed(self):
        """重复写自己的条码不该误报（约束的 domain 里用 ('id','!=',id) 排除了自身）"""
        own = self.test_record.barcode
        self.test_record.write({'barcode': own, 'state': 'done'})
        self.assertEqual(self.test_record.barcode, own)

    def test_barcode_change_to_new_value_is_allowed(self):
        """改成谁都没用过的条码 → 正常写入"""
        other = self.MyModel.create({'barcode': 'TEST021'})
        other.barcode = 'TEST022'
        self.assertEqual(other.barcode, 'TEST022')

    def test_two_records_with_different_barcodes_coexist(self):
        """不同条码的订单可以同时存在"""
        other = self.MyModel.create({'barcode': 'TEST023'})
        self.assertNotEqual(self.test_record.barcode, other.barcode)

    # ---------------- 明细行级联 ----------------

    def test_lines_are_cascade_deleted(self):
        """订单删除时明细行（ondelete='cascade'）一起被删掉"""
        line = self.env['l.sale.order.line'].create({
            'order_id': self.test_record.id,
            'name': '明细1',
        })
        self.assertIn(line, self.test_record.line_ids)
        self.test_record.unlink()
        self.assertFalse(line.exists())
