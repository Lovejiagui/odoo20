{
    'name': 'GLM AI Provider',
    'summary': '把 Odoo 20 的 AI 请求路由到智谱 GLM（OpenAI 兼容接口）',
    'description': """
复用 Odoo 企业版原生的 AI Agent / AI 字段 / 服务器动作能力，但推理请求改发到
智谱 GLM 的 OpenAI 兼容端点，不用 Odoo IAP 点数。

实现原理：Odoo 20 的所有 AI 推理都从 ai.session._get_completions 出口，本模块
继承并改写一个方法，把 Odoo 的消息/工具格式翻译成 OpenAI Chat Completions 格式，
再把 GLM 的回复翻译回 Odoo 的 AIMessageParts 结构。

配置（Settings → 技术 → 系统参数）：
  l_ai_glm.api_key      智谱开放平台的 API Key（留空则回退到 Odoo 原生 AI）
  l_ai_glm.endpoint     默认 https://open.bigmodel.cn/api/paas/v4
  l_ai_glm.model        默认 glm-4.6
  l_ai_glm.enabled      是否启用（默认 1）
""",
    'version': '20.0.1.1.0',
    'license': 'LGPL-3',
    'author': 'Lovejiagui',
    'depends': ['ai', 'iap'],
    'data': [],
    'installable': True,
    'application': False,
}
