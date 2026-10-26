from datetime import date, timedelta

from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestLTaskTag(TransactionCase):
    """l.task.tag：名称唯一约束（Odoo 19 用 models.Constraint 声明，老的 _sql_constraints 已移除）"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Tag = cls.env['l.task.tag']

    def test_create_tag(self):
        tag = self.Tag.create({'name': '紧急', 'color': 3})
        self.assertEqual(tag.name, '紧急')
        self.assertEqual(tag.color, 3)

    def test_name_is_required(self):
        """标签名必填，不传建不出来"""
        self.assertTrue(self.Tag._fields['name'].required)
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            self.Tag.create({})

    def test_name_must_be_unique(self):
        """重名标签抛 IntegrityError（UNIQUE 约束 l_task_tag_name_uniq）"""
        self.Tag.create({'name': '重复标签'})
        self.env.flush_all()
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            self.Tag.create({'name': '重复标签'})

    def test_different_names_are_fine(self):
        """不同名字的标签可以共存"""
        first = self.Tag.create({'name': '标签A'})
        second = self.Tag.create({'name': '标签B'})
        self.assertNotEqual(first, second)

    def test_tags_are_ordered_by_name(self):
        """_order = 'name'，标签按名称排序"""
        zzz = self.Tag.create({'name': 'zzz-tag'})
        aaa = self.Tag.create({'name': 'aaa-tag'})
        found = self.Tag.search([('id', 'in', (zzz + aaa).ids)])
        self.assertEqual(found.ids, [aaa.id, zzz.id])


@tagged('post_install', '-at_install')
class TestLTask(TransactionCase):
    """l.task：默认值、日期约束、状态流转、标签、排序、归档"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Task = cls.env['l.task']

    def _make_task(self, **vals):
        vals.setdefault('name', '测试任务')
        return self.Task.create(vals)

    # ---------------- 默认值 ----------------

    def test_default_values(self):
        task = self._make_task()
        self.assertEqual(task.state, 'draft')
        self.assertEqual(task.priority, '0')
        self.assertAlmostEqual(task.progress, 0.0)
        self.assertTrue(task.active)
        self.assertEqual(task.user_id, self.env.user)
        self.assertEqual(task.date_start, date.today())
        self.assertEqual(task.sequence, 10)
        self.assertFalse(task.date_end)

    def test_name_is_required(self):
        """任务名必填，不传建不出来"""
        self.assertTrue(self.Task._fields['name'].required)
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            self.Task.create({})

    def test_state_selection_values(self):
        selection = dict(self.Task._fields['state'].selection)
        self.assertEqual(set(selection), {'draft', 'doing', 'done', 'cancel'})
        self.assertEqual(selection['doing'], '进行中')

    # ---------------- 日期约束 ----------------

    def test_end_date_before_start_date_raises(self):
        """结束日期早于开始日期 → ValidationError"""
        with self.assertRaises(ValidationError):
            self._make_task(
                date_start=date.today(),
                date_end=date.today() - timedelta(days=1),
            )

    def test_same_start_and_end_date_is_allowed(self):
        """起止同一天不算越界"""
        task = self._make_task(date_start=date.today(), date_end=date.today())
        self.assertEqual(task.date_start, task.date_end)

    def test_only_one_date_set_is_allowed(self):
        """只填一边时不做校验（约束要求两边都有值）"""
        task = self._make_task(
            date_start=False,
            date_end=date.today() - timedelta(days=30),
        )
        self.assertFalse(task.date_start)
        self.assertTrue(task.date_end)

    def test_date_constraint_also_fires_on_write(self):
        """改日期时同样触发校验"""
        task = self._make_task(
            date_start=date.today(),
            date_end=date.today() + timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            task.write({'date_end': date.today() - timedelta(days=1)})

    # ---------------- 状态流转 ----------------

    def test_action_start(self):
        task = self._make_task()
        task.action_start()
        self.assertEqual(task.state, 'doing')

    def test_action_done_sets_progress_to_100(self):
        task = self._make_task()
        task.action_start()
        task.action_done()
        self.assertEqual(task.state, 'done')
        self.assertAlmostEqual(task.progress, 100.0)

    def test_action_cancel(self):
        task = self._make_task()
        task.action_cancel()
        self.assertEqual(task.state, 'cancel')

    def test_action_reset_goes_back_to_draft(self):
        task = self._make_task()
        task.action_done()
        task.action_reset()
        self.assertEqual(task.state, 'draft')
        # 注意：action_reset 只改状态，不会把 progress 归零（当前行为，写测试固化）
        self.assertAlmostEqual(task.progress, 100.0)

    def test_actions_work_on_multiple_records(self):
        """列表视图上按钮可以批量执行"""
        tasks = self._make_task() | self._make_task(name='任务2')
        tasks.action_start()
        self.assertEqual(set(tasks.mapped('state')), {'doing'})
        tasks.action_cancel()
        self.assertEqual(set(tasks.mapped('state')), {'cancel'})

    # ---------------- 标签 ----------------

    def test_tags_many2many(self):
        tags = self.env['l.task.tag'].create([{'name': '后端'}, {'name': '前端'}])
        task = self._make_task(tag_ids=[(6, 0, tags.ids)])
        self.assertEqual(len(task.tag_ids), 2)
        self.assertEqual(set(task.tag_ids.mapped('name')), {'后端', '前端'})

    # ---------------- 排序 ----------------

    def test_ordering_sequence_then_id_desc(self):
        """_order = 'sequence, id desc'：先按 sequence 升序，再按 id 降序"""
        first = self._make_task(name='顺序1', sequence=5)
        high_earlier = self._make_task(name='顺序2', sequence=20)
        high_later = self._make_task(name='顺序3', sequence=20)
        found = self.Task.search([
            ('id', 'in', (first + high_earlier + high_later).ids),
        ])
        self.assertEqual(found.ids, [first.id, high_later.id, high_earlier.id])
        self.assertEqual(self.Task._order, 'sequence, id desc')

    # ---------------- 归档 ----------------

    def test_archived_task_is_hidden_by_default(self):
        """active=False 之后默认搜不到，去掉 active_test 才能搜到"""
        task = self._make_task()
        self.assertIn(task, self.Task.search([]))
        task.active = False
        self.assertNotIn(task, self.Task.search([]))
        self.assertIn(task, self.Task.with_context(active_test=False).search([]))
