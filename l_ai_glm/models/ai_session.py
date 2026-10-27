# -*- coding: utf-8 -*-
"""接管 Odoo 20 的 AI 推理出口。

企业在 ai_session.py 里的实现是：

    def _get_completions(self, messages, instructions, tools, timeout, **options):
        params = {'messages': ..., 'instructions': ..., 'tools': ..., **options}
        return call_odoo_ai(self.env, "1/get_completions_sync", params, timeout=timeout)

只有这一个出口负责聊天、AI 字段、server action 的推理，所以这里改写它即可，
不需要去动 ai 模块的其他代码。返回值必须保持原契约：

    {'result': {'role': 'assistant', 'content': [part, ...]}}
"""

import logging

from odoo import _, models
from odoo.exceptions import UserError

from .glm_client import GLMError, call_glm, get_client_config, glm_message_to_parts

_logger = logging.getLogger(__name__)

# 这些能力本模块暂时不接管，交给 Odoo 原生实现处理
UNSUPPORTED_OPTIONS = ('image_generation',)


class AiSession(models.Model):
    _inherit = 'ai.session'

    def _get_completions(self, messages, instructions, tools=None, timeout=60, **options):
        api_key, endpoint, model, enabled = get_client_config(self.env)

        if not enabled or not api_key or any(options.get(key) for key in UNSUPPORTED_OPTIONS):
            # 没配置 / 没启用 / 遇到不支持的能力 -> 走原生实现
            if not (enabled and api_key):
                _logger.info('l_ai_glm 未配置或未启用（enabled=%s, api_key=%s），回退到 Odoo 原生 AI',
                             enabled, bool(api_key))
            return super()._get_completions(
                messages, instructions, tools, timeout=timeout, **options
            )

        _logger.info('l_ai_glm 接管 AI 请求：model=%s, messages=%s 条, tools=%s',
                     model, len(messages or []), bool(tools))

        # 结构化输出：把 JSON Schema 说明塞进 instructions，GLM 侧开 json_object 模式
        effective_instructions = instructions
        if schema := options.get('schema'):
            effective_instructions = (
                f'{instructions or ""}\n\n'
                '你必须使用合法的 JSON 回答，且必须严格符合下面的 JSON Schema：\n'
                f'{schema}'
            )

        try:
            glm_message = call_glm(
                self.env,
                api_key,
                endpoint,
                model,
                messages,
                effective_instructions,
                tools,
                timeout=timeout,
                **options,
            )
        except GLMError as err:
            _logger.warning('GLM 调用失败: %s', err)
            raise UserError(_('调用 GLM 失败：%s', err)) from err

        parts = glm_message_to_parts(glm_message)
        _logger.info('l_ai_glm GLM 调用成功，返回 %s 个 part', len(parts))
        return {
            'result': {
                'role': 'assistant',
                'content': parts,
            },
        }
