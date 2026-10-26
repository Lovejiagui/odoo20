from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LTaskTag(models.Model):
    _name = 'l.task.tag'
    _description = '任务标签'
    _order = 'name'

    name = fields.Char(string='标签名', required=True)
    color = fields.Integer(string='颜色')

    # Odoo 19 新写法：模型的 SQL 约束用 models.Constraint 声明，
    # 老的 _sql_constraints 列表已经不再支持。
    _name_uniq = models.Constraint(
        'UNIQUE (name)',
        '标签名不能重复。',
    )


class LTask(models.Model):
    _name = 'l.task'
    _description = '任务'
    _order = 'sequence, id desc'

    name = fields.Char(string='任务名', required=True)
    user_id = fields.Many2one('res.users', string='负责人', default=lambda self: self.env.user)
    description = fields.Html(string='描述')

    state = fields.Selection(
        [('draft', '待办'), ('doing', '进行中'), ('done', '已完成'), ('cancel', '已取消')],
        string='状态', default='draft', required=True,
    )
    priority = fields.Selection(
        [('0', '普通'), ('1', '重要'), ('2', '紧急'), ('3', '非常紧急')],
        string='优先级', default='0',
    )

    date_start = fields.Date(string='开始日期', default=fields.Date.today)
    date_end = fields.Date(string='结束日期')
    progress = fields.Float(string='进度', default=0.0)

    tag_ids = fields.Many2many('l.task.tag', string='标签')
    color = fields.Integer(string='颜色')
    sequence = fields.Integer(string='排序', default=10)
    active = fields.Boolean(string='启用', default=True)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for task in self:
            if task.date_start and task.date_end and task.date_end < task.date_start:
                raise ValidationError('结束日期不能早于开始日期。')

    def action_start(self):
        self.write({'state': 'doing'})

    def action_done(self):
        self.write({'state': 'done', 'progress': 100.0})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_reset(self):
        self.write({'state': 'draft'})
