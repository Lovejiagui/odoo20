from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

# Odoo 20 已移除 ir.model.access 和 perm_* 字段，权限统一由 ir.access.operation 表达，
# operation 是 'crud' 的子集字符串（如 'cru'），同一组的各条记录按并集合并。
# 权限矩阵：模型名 -> (操作员组 operation 并集, 管理员组 operation 并集)
ACL_MATRIX = {
    'l.sale.order': ({'c', 'r', 'u'}, {'c', 'r', 'u', 'd'}),
    'l.sale.order.line': ({'c', 'r', 'u', 'd'}, {'c', 'r', 'u', 'd'}),
    'l.sale.order.wizard': ({'c', 'r', 'u', 'd'}, {'c', 'r', 'u', 'd'}),
    'l.task': ({'c', 'r', 'u'}, {'c', 'r', 'u', 'd'}),
    'l.task.tag': ({'r'}, {'c', 'r', 'u', 'd'}),
}


@tagged('post_install', '-at_install')
class TestAccessRights(TransactionCase):
    """demo_test_new 的权限控制：

    * 不属于本模块任何组的用户（仅 base.group_user）一律 AccessError；
    * 操作员：能建单/改草稿单，不能删单、不能改已完成单；任务只看自己的；标签只读；
    * 管理员：全部数据、全部操作（组继承 + 记录规则 OR 合并实现）。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_operator = cls.env.ref('demo_test_new.l_group_order_user')
        cls.group_manager = cls.env.ref('demo_test_new.l_group_order_manager')
        # Odoo 19 里 res.users 的分组字段叫 group_ids（旧名 groups_id 已移除）
        cls.plain_user = cls._create_user('demo_test_new_plain', [
            cls.env.ref('base.group_user').id,
        ])
        cls.operator = cls._create_user('demo_test_new_operator', [cls.group_operator.id])
        cls.manager = cls._create_user('demo_test_new_manager', [cls.group_manager.id])

    @classmethod
    def _create_user(cls, login, group_ids):
        return cls.env['res.users'].create({
            'name': login,
            'login': login,
            'group_ids': [(6, 0, group_ids)],
        })

    def _accesses(self, model_name, group):
        model = self.env['ir.model'].search([('model', '=', model_name)], limit=1)
        self.assertTrue(model, f'模型 {model_name} 没注册到 ir.model')
        return self.env['ir.access'].search([
            ('model_id', '=', model.id),
            ('group_id', '=', group.id),
        ])

    # ---------------- ACL 静态矩阵 ----------------

    def test_acl_matrix(self):
        """每个模型对两个组都有 ir.access 记录，且各条 operation 的并集与矩阵一致"""
        for model_name, (operator_ops, manager_ops) in ACL_MATRIX.items():
            for group, expected in ((self.group_operator, operator_ops),
                                    (self.group_manager, manager_ops)):
                accesses = self._accesses(model_name, group)
                self.assertTrue(accesses, f'{model_name} 缺少 {group.name} 的访问规则')
                actual = set(''.join(accesses.mapped('operation')))
                self.assertEqual(actual, expected,
                                 f'{model_name} 对 {group.name} 的权限应为 {expected}，实际 {actual}')

    def test_admin_is_in_manager_group(self):
        """收紧 ACL 后系统管理员必须还在管理员组里，否则后台数据全看不到"""
        admin = self.env.ref('base.user_admin')
        self.assertIn(admin, self.group_manager.all_user_ids)

    def test_manager_group_implies_operator_group(self):
        self.assertIn(self.group_operator, self.group_manager.implied_ids)

    def test_menu_is_restricted_to_module_groups(self):
        menu = self.env.ref('demo_test_new.l_sale_order_menu_root')
        # Odoo 19 里 ir.ui.menu 的分组字段叫 group_ids（旧名 groups_id 已移除）
        self.assertIn(self.group_operator, menu.group_ids)

    # ---------------- 无组用户 ----------------

    def test_plain_user_has_no_access(self):
        """只属于 base.group_user 的用户对 5 个业务模型一律吃 AccessError"""
        for model_name in ACL_MATRIX:
            with self.assertRaises(AccessError), mute_logger('odoo.orm.models',
                                                             'odoo.addons.base.models.ir_rule'):
                self.env[model_name].with_user(self.plain_user).search([])

    # ---------------- l.sale.order ----------------

    def test_operator_can_create_and_write_draft_order(self):
        order = self.env['l.sale.order'].with_user(self.operator).create({
            'barcode': 'ACL-OP-1',
            'payment_type': 'v_1',
        })
        self.assertEqual(order.state, 'draft')
        self.assertIn(order, self.env['l.sale.order'].with_user(self.operator).search([]))

    def test_operator_cannot_write_done_order(self):
        """记录规则：操作员只能改草稿，已完成单只允许管理员改"""
        order = self.env['l.sale.order'].with_user(self.operator).create({
            'barcode': 'ACL-OP-2',
        })
        order.state = 'done'  # 以超级用户身份推进状态

        # 读还是允许的（可读全部规则）
        self.assertIn(order, self.env['l.sale.order'].with_user(self.operator).search([]))
        with self.assertRaises(AccessError), mute_logger('odoo.addons.base.models.ir_rule'):
            order.with_user(self.operator).write({'payment_type': 'v_2'})

    def test_operator_cannot_unlink_order(self):
        order = self.env['l.sale.order'].with_user(self.operator).create({
            'barcode': 'ACL-OP-3',
        })
        with self.assertRaises(AccessError), mute_logger('odoo.orm.models'):
            order.with_user(self.operator).unlink()

    def test_manager_can_write_done_and_unlink(self):
        order = self.env['l.sale.order'].create({'barcode': 'ACL-MGR-1', 'state': 'done'})
        order.with_user(self.manager).write({'payment_type': 'v_3'})
        self.assertEqual(order.payment_type, 'v_3')
        order.with_user(self.manager).unlink()
        self.assertFalse(order.exists())

    # ---------------- 明细行 ----------------

    def test_operator_can_edit_line_of_draft_order_only(self):
        draft = self.env['l.sale.order'].with_user(self.operator).create({'barcode': 'ACL-LINE-1'})
        done = self.env['l.sale.order'].create({'barcode': 'ACL-LINE-2', 'state': 'done'})

        line = self.env['l.sale.order.line'].with_user(self.operator).create({
            'order_id': draft.id, 'qty': 1,
        })
        line.with_user(self.operator).write({'qty': 2})
        self.assertEqual(line.qty, 2)

        done_line = self.env['l.sale.order.line'].create({'order_id': done.id, 'qty': 1})
        done_line.with_user(self.manager).write({'qty': 5})
        self.assertEqual(done_line.qty, 5)
        with self.assertRaises(AccessError), mute_logger('odoo.addons.base.models.ir_rule'):
            done_line.with_user(self.operator).write({'qty': 9})

    # ---------------- l.task ----------------

    def test_task_operator_sees_only_his_own(self):
        own = self.env['l.task'].with_user(self.operator).create({'name': '操作员的任务'})
        other = self.env['l.task'].with_user(self.manager).create({'name': '管理员的任务'})

        operator_tasks = self.env['l.task'].with_user(self.operator).search([])
        self.assertIn(own, operator_tasks)
        self.assertNotIn(other, operator_tasks)

        manager_tasks = self.env['l.task'].with_user(self.manager).search([])
        self.assertIn(own, manager_tasks)
        self.assertIn(other, manager_tasks)

    def test_operator_cannot_unlink_task(self):
        task = self.env['l.task'].with_user(self.operator).create({'name': '操作员的任务2'})
        with self.assertRaises(AccessError), mute_logger('odoo.orm.models'):
            task.with_user(self.operator).unlink()
        task.with_user(self.manager).unlink()
        self.assertFalse(task.exists())

    # ---------------- l.task.tag ----------------

    def test_tag_is_read_only_for_operator(self):
        tag = self.env['l.task.tag'].create({'name': '管理员建的标签'})
        self.assertIn(tag, self.env['l.task.tag'].with_user(self.operator).search([]))
        with self.assertRaises(AccessError), mute_logger('odoo.orm.models'):
            self.env['l.task.tag'].with_user(self.operator).create({'name': '操作员建的标签'})

        managed = self.env['l.task.tag'].with_user(self.manager).create({'name': '管理员再建一个'})
        self.assertTrue(managed.exists())

    # ---------------- 向导 ----------------

    def test_wizard_respects_order_rules(self):
        """向导批量改单：草稿单操作员可用，已完成单只能管理员改"""
        draft = self.env['l.sale.order'].with_user(self.operator).create({'barcode': 'ACL-WIZ-1'})
        done = self.env['l.sale.order'].create({'barcode': 'ACL-WIZ-2', 'state': 'done'})

        draft_wizard = self.env['l.sale.order.wizard'].with_user(self.operator).create({
            'order_ids': draft.ids,
            'payment_type': 'v_2',
        })
        draft_wizard.action_confirm()
        self.assertEqual(draft.payment_type, 'v_2')

        done_wizard = self.env['l.sale.order.wizard'].with_user(self.operator).create({
            'order_ids': done.ids,
            'payment_type': 'v_2',
        })
        with self.assertRaises(AccessError), mute_logger('odoo.addons.base.models.ir_rule'):
            done_wizard.action_confirm()
