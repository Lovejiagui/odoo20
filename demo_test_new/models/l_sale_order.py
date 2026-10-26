
import secrets
import uuid

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# 随机条码：12 位纯数字，撞号就重抽
BARCODE_LENGTH = 12
BARCODE_ALPHABET = '0123456789'
BARCODE_MAX_TRY = 5


class LSaleOrder(models.Model):
    _name = 'l.sale.order'
    _description = 'l Sale Order'
    _order = 'id desc'

    # 单号改由人工录入（必填由表单视图约束，ORM 层面不强求，方便批量导入/测试）
    name = fields.Char(string='单号', help='手工录入的单号，如 SO20260001')
    validate_date = fields.Date(string='有效期', default=fields.Date.today())
    payment_type = fields.Selection([('v_1', '立即付款'), ('v_2', '7天'), ('v_3', '15天')], string='付款条款')
    partner_id = fields.Many2one('res.partner', string='客户')
    line_ids = fields.One2many('l.sale.order.line', 'order_id')
    note = fields.Html(string='备注')
    state = fields.Selection([('draft', '草稿'), ('done', '完成')], string='订单状态', default='draft')
    # 条码改为系统随机生成：默认自动生成 + 界面只读 + 复制单据时另起一个
    barcode = fields.Char(
        string='条码', required=True, readonly=True, copy=False,
        default=lambda self: self._generate_barcode(),
    )

    carousel_dummy = fields.Char(string="轮播占位字段")

    @api.model
    def _generate_barcode(self):
        """随机生成一条没用过的条码。

        secrets 而不是 random：条码算业务标识，不希望被预测。
        撞号概率极低，但仍循环重试；极端情况下退回 uuid 兜底（长度对齐）。
        """
        for _ in range(BARCODE_MAX_TRY):
            candidate = ''.join(secrets.choice(BARCODE_ALPHABET) for _ in range(BARCODE_LENGTH))
            if not self.search_count([('barcode', '=', candidate)]):
                return candidate
        # 一路撞号的兜底：uuid 取前 BARCODE_LENGTH 位
        fallback = uuid.uuid4().hex.upper()[:BARCODE_LENGTH]
        return fallback

    #数据校验
    @api.constrains('barcode')
    def constrains_barcode(self):
        for record in self:
            if not record.barcode:
                continue
            # 条码查重，注意要排除自身
            domain = [('barcode', '=', record.barcode)]
            if isinstance(record.id, int):
                domain.append(('id', '!=', record.id))
            if self.env['l.sale.order'].search_count(domain):
                raise ValidationError('订单条码不能重复')
#数据校验
    @api.constrains('name')
    def constrains_name(self):
        for record in self:
            if not record.name:
                continue
            # 单号查重，注意要排除自身
            domain = [('name', '=', record.name)]
            if isinstance(record.id, int):
                domain.append(('id', '!=', record.id))
            if self.env['l.sale.order'].search_count(domain):

                raise ValidationError('订单单号不能重复')

# 新增多对多字段，关联轮播模型
#    carousel_slide_ids = fields.Many2many(
#        comodel_name='website.carousel.slide',
#        string="轮播幻灯片预览",
#        # 自动读取所有active=True的幻灯片
#        domain="[('active','=',True)]",
#    )

#    # 自动填充：每次打开单据，自动加载全部启用幻灯片
#   @api.model
#    def default_get(self, fields):
#        res = super().default_get(fields)
#        slides = self.env['website.carousel.slide'].sudo().search([('active','=',True)])
#        res['carousel_slide_ids'] = slides.ids
#        return res

