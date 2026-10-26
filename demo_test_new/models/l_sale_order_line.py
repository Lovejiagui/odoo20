from odoo import api, models, fields
from odoo.fields import Command

# 明细行默认套用的销售税率（%）。
# 这里只保留"税率"这个业务值，税项记录本身按税率动态解析，不再写死名称。
TARGET_TAX_AMOUNT = 21.0


class LSaleOrderLine(models.Model):
    _name = 'l.sale.order.line'
    _description = '测试销售单明细行'

    name = fields.Char(string='明细行')
    order_id = fields.Many2one('l.sale.order',ondelete='cascade')
    product_id = fields.Many2one('product.product')
    price_unit = fields.Float(string='单价', digits='Product Unit')
    amount_total = fields.Float(string='总价', digits=(16,3))
    qty = fields.Float(string='数量')
    tax_ids = fields.Many2many('account.tax',string='税项')

    def _get_target_tax(self, amount):
        """按税率动态解析出对应的销售税项，查不到才新建。

        Odoo 19 的 account.tax 有 _constrains_name（同公司内税名唯一），
        原来每次都用硬编码的 name='21%' 去新建，撞上账套里已存在的同号税项就会抛
        ValidationError，所以这里先查后用。
        """
        company = self.env.company
        Tax = self.env['account.tax']
        tax = Tax.search([
            ('amount', '=', amount),
            ('amount_type', '=', 'percent'),
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not tax:
            tax = Tax.create({
                # 名称也按税率动态拼出来，不写死字面量
                'name': f'{amount:g}%',
                'amount': amount,
                'amount_type': 'percent',
                'type_tax_use': 'sale',
                'company_id': company.id,
            })
        return tax

    def button_add(self):
        """操作tax_ids：把明细行的税项换成目标税率的销售税（整体替换，点多次结果一致）"""
        tax = self._get_target_tax(TARGET_TAX_AMOUNT)
        self.tax_ids = [Command.set(tax.ids)]
