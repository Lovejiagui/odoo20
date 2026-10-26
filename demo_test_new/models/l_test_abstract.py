

from odoo import fields, models,api

class LTestAbstract(models.AbstractModel):
    _name = 'l.test.abstract'
    _description = '审批状态混入（抽象模型）'

    approve_state = fields.Selection([('draft','草稿'),('waiting','等待审批'),
                                      ('agree','同意'),('refuse','拒绝')],string='审批状态')