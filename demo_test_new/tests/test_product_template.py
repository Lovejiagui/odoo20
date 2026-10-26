from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProductTemplateExtension(TransactionCase):
    """models/product_template.py：继承 product.template，并混入抽象模型 l.test.abstract"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Product = cls.env['product.template']

    def test_l_barcode_field_round_trip(self):
        """自己加的 l_barcode 字段可写可读"""
        product = self.Product.create({'name': '测试产品', 'l_barcode': 'PT-001'})
        self.assertEqual(product.l_barcode, 'PT-001')
        product.l_barcode = 'PT-002'
        self.assertEqual(product.l_barcode, 'PT-002')

    def test_abstract_mixin_is_applied(self):
        """抽象模型 l.test.abstract 的 approve_state 真的挂到了 product.template 上"""
        self.assertIn('approve_state', self.Product._fields)
        product = self.Product.create({'name': '测试产品2'})
        self.assertFalse(product.approve_state)
        product.approve_state = 'agree'
        self.assertEqual(product.approve_state, 'agree')

    def test_approve_state_selection_values(self):
        """混入字段的选值原样带过来"""
        selection = dict(self.Product._fields['approve_state'].selection)
        self.assertEqual(set(selection), {'draft', 'waiting', 'agree', 'refuse'})
        self.assertEqual(selection['draft'], '草稿')
        self.assertEqual(selection['agree'], '同意')

    def test_abstract_model_has_no_table(self):
        """l.test.abstract 是抽象模型，没有自己的表，只作为混入用"""
        self.assertTrue(self.env['l.test.abstract']._abstract)
