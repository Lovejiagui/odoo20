from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestPermissionAssignment(TransactionCase):
    """订单系统的权限分配：res.users 上的两个角色开关。

    重点守护两件事：
    1. 开关只增删本模块的两个组，绝不整体替换 group_ids
       （否则会把用户原有的其他权限组清空，等于误伤）；
    2. 只有订单管理员能操作，操作员既看不到字段也写不了，不能自己提权。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_operator = cls.env.ref('demo_test_new.l_group_order_user')
        cls.group_manager = cls.env.ref('demo_test_new.l_group_order_manager')
        cls.group_internal = cls.env.ref('base.group_user')
        cls.operator = cls._create_user('perm_operator', [cls.group_operator.id])
        cls.manager = cls._create_user('perm_manager', [cls.group_manager.id])
        cls.target = cls._create_user('perm_target', [cls.group_internal.id])

    @classmethod
    def _create_user(cls, login, group_ids):
        # Odoo 19 里 res.users 的分组字段叫 group_ids
        return cls.env['res.users'].create({
            'name': login,
            'login': login,
            'group_ids': [Command.set(group_ids)],
        })

    # ---------------- 授权行为 ----------------

    def test_grant_operator_only(self):
        self.assertFalse(self.target.l_is_order_user)
        self.target.with_user(self.manager).write({'l_is_order_user': True})
        self.assertTrue(self.target.l_is_order_user)
        self.assertIn(self.group_operator, self.target.group_ids)
        self.assertNotIn(self.group_manager, self.target.group_ids)

    def test_grant_manager_implies_operator(self):
        """勾管理员会连带勾上操作员（管理员组隐含操作员组），界面与实际权限一致"""
        self.target.with_user(self.manager).write({'l_is_order_manager': True})
        self.assertIn(self.group_manager, self.target.group_ids)
        self.assertIn(self.group_operator, self.target.group_ids)
        self.assertTrue(self.target.l_is_order_user)

    def test_uncheck_manager_downgrades_to_operator(self):
        """取消管理员=降级成操作员，而不是把权限一次性清零"""
        self.target.with_user(self.manager).write({'l_is_order_manager': True})
        self.target.with_user(self.manager).write({'l_is_order_manager': False})
        self.assertFalse(self.target.l_is_order_manager)
        self.assertTrue(self.target.l_is_order_user)
        self.assertNotIn(self.group_manager, self.target.group_ids)

    def test_other_groups_are_never_cleared(self):
        """反例守护：反复切换开关后，用户原有的组必须原样保留"""
        self.target.with_user(self.manager).write({'l_is_order_manager': True})
        self.assertIn(self.group_internal, self.target.group_ids)
        self.target.with_user(self.manager).write({'l_is_order_manager': False})
        self.assertIn(self.group_internal, self.target.group_ids)
        self.target.with_user(self.manager).write({'l_is_order_user': False})
        self.assertEqual(self.target.group_ids, self.group_internal)

    def test_switch_follows_native_group_ids(self):
        """用原生权限控件改组时，开关也要跟着重算（@api.depends('group_ids')）"""
        self.target.with_user(self.manager).write({'l_is_order_manager': True})
        self.target.write({'group_ids': [Command.clear()]})
        self.assertFalse(self.target.l_is_order_user)
        self.assertFalse(self.target.l_is_order_manager)

    # ---------------- 提权防护 ----------------

    def test_operator_cannot_grant(self):
        with self.assertRaises(AccessError), mute_logger('odoo.orm.models',
                                                         'odoo.addons.base.models.ir_rule'):
            self.target.with_user(self.operator).write({'l_is_order_user': True})

    def test_operator_cannot_self_elevate_via_native_groups(self):
        """绕开开关直接改原生 group_ids 给自己加管理员组，同样要被拒"""
        with self.assertRaises(AccessError), mute_logger('odoo.orm.models'):
            self.operator.with_user(self.operator).write({
                'group_ids': [Command.link(self.group_manager.id)],
            })

    def test_switch_field_is_hidden_from_operator(self):
        fields_op = self.env['res.users'].with_user(self.operator).fields_get()
        fields_mgr = self.env['res.users'].with_user(self.manager).fields_get()
        self.assertNotIn('l_is_order_user', fields_op)
        self.assertNotIn('l_is_order_manager', fields_op)
        self.assertIn('l_is_order_user', fields_mgr)
        self.assertIn('l_is_order_manager', fields_mgr)

    # ---------------- ACL ----------------

    def test_res_users_acl_for_manager(self):
        """订单管理员必须能读写 res.users，否则权限分配页根本打不开"""
        acl = self.env['ir.model.access'].search([
            ('model_id.model', '=', 'res.users'),
            ('group_id', '=', self.group_manager.id),
        ], limit=1)
        self.assertTrue(acl, '缺 res.users 给订单管理员组的访问规则')
        self.assertTrue(acl.perm_read)
        self.assertTrue(acl.perm_write)
        # 不给建/删，避免管理员乱开账号
        self.assertFalse(acl.perm_create)
        self.assertFalse(acl.perm_unlink)
