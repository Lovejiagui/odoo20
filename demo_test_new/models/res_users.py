# -*- coding: utf-8 -*-
"""给 res.users 加订单系统的角色开关。

设计要点：
1. 不能直接在表单里再放一个 group_ids（Odoo 19 的 access_rights 页已经有原生的
   res_user_group_ids 控件），否则前端勾选框提交 (6,0,ids) 命令会把用户其他组清空。
2. 所以这里用两个 Boolean（compute + inverse），inverse 里只对 group_ids 做
   link / unlink 增删，绝不整体替换，保证不影响用户的其他任何权限组。
"""

from odoo import api, fields, models
from odoo.fields import Command


class ResUsers(models.Model):
    _inherit = 'res.users'

    l_is_order_user = fields.Boolean(
        string='订单操作员',
        compute='_compute_l_order_groups',
        inverse='_inverse_l_is_order_user',
        groups='demo_test_new.l_group_order_manager',
        help='勾选后加入「订单操作员」组：可建单、可改自己的草稿单，但不能删单。',
    )
    l_is_order_manager = fields.Boolean(
        string='订单管理员',
        compute='_compute_l_order_groups',
        inverse='_inverse_l_is_order_manager',
        groups='demo_test_new.l_group_order_manager',
        help='勾选后加入「订单管理员」组：订单模块全部权限（该组隐含操作员组）。',
    )

    def _l_order_groups(self):
        """返回 (操作员组, 管理员组)"""
        return (
            self.env.ref('demo_test_new.l_group_order_user'),
            self.env.ref('demo_test_new.l_group_order_manager'),
        )

    # 声明依赖：group_ids 一变（无论是本字段的 inverse 改的，还是原生权限控件改的）
    # 两个开关都要重算，避免界面上显示陈旧的勾选状态
    @api.depends('group_ids')
    def _compute_l_order_groups(self):
        g_user, g_manager = self._l_order_groups()
        for user in self:
            # 判断归属要用 all_group_ids（含隐含组）：管理员组隐含操作员组，
            # 只勾管理员时 group_ids 里并没有操作员组，但实际已拥有其权限。
            user.l_is_order_user = g_user in user.all_group_ids
            user.l_is_order_manager = g_manager in user.all_group_ids

    # 两个开关各用各的 inverse：只依据「自己」的值增删对应的组。
    # 千万不要共用一个 inverse 去读另一个字段的值——非存储字段的缓存是否失效
    # 取决于中间有没有人读过它，那样行为会时好时坏（写两个字段时结果随机）。
    def _inverse_l_is_order_user(self):
        g_user, g_manager = self._l_order_groups()
        for user in self:
            if user.l_is_order_user:
                if g_user not in user.group_ids:
                    user.group_ids = [Command.link(g_user.id)]
            else:
                cmds = [Command.unlink(g_user.id)] if g_user in user.group_ids else []
                # 管理员组隐含操作员组，"只留管理员、去掉操作员"是自相矛盾的状态，
                # 所以取消操作员时若还挂着管理员，一并去掉，避免界面显示与实际不符
                if g_manager in user.group_ids:
                    cmds.append(Command.unlink(g_manager.id))
                if cmds:
                    user.group_ids = cmds

    def _inverse_l_is_order_manager(self):
        g_user, g_manager = self._l_order_groups()
        for user in self:
            if user.l_is_order_manager:
                cmds = []
                if g_manager not in user.group_ids:
                    cmds.append(Command.link(g_manager.id))
                # 管理员隐含操作员，补上操作员让界面与实际权限一致
                if g_user not in user.group_ids:
                    cmds.append(Command.link(g_user.id))
                if cmds:
                    user.group_ids = cmds
            else:
                # 取消管理员 = 降级成操作员，不是清空全部权限
                if g_manager in user.group_ids:
                    user.group_ids = [Command.unlink(g_manager.id)]
