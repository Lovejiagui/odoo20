from odoo import api, fields, models
from odoo.exceptions import UserError


class LSaleOrderWizard(models.TransientModel):
    _name = 'l.sale.order.wizard'
    _description = '销售单批量处理向导'

    # 由 context 里的 active_ids 自动带出列表页勾选的单据
    order_ids = fields.Many2many(
        comodel_name='l.sale.order',
        string='待处理单据',
        default=lambda self: self.env.context.get('active_ids') or [],
    )
    order_count = fields.Integer(string='单据数量', compute='_compute_order_count')

    # 以下三个字段留空表示「不修改」
    payment_type = fields.Selection(
        [('v_1', '立即付款'), ('v_2', '7天'), ('v_3', '15天')],
        string='付款条款',
    )
    validate_date = fields.Date(string='有效期')
    remark = fields.Text(string='处理备注')

    @api.depends('order_ids')
    def _compute_order_count(self):
        for wizard in self:
            wizard.order_count = len(wizard.order_ids)

    def action_confirm(self):
        """把向导里填了的字段批量写回选中单据，然后关闭弹窗。"""
        self.ensure_one()
        if not self.order_ids:
            raise UserError('请先在列表中勾选需要处理的单据。')

        vals = {}
        if self.payment_type:
            vals['payment_type'] = self.payment_type
        if self.validate_date:
            vals['validate_date'] = self.validate_date
        if self.remark:
            vals['note'] = self.remark

        if not vals:
            raise UserError('请至少填写一项要修改的内容。')

        self.order_ids.write(vals)
        return {'type': 'ir.actions.act_window_close'}
