from odoo import fields, models, api

class ProductTemplate(models.Model):
    _name = 'product.template'
    _inherit = ['product.template','l.test.abstract']


    l_barcode = fields.Char(string='我的条码')


