# -*- coding: utf-8 -*-
"""接管 Odoo 20 的 AI 推理出口。

企业版有两条推理链路，这里都改写成 GLM：

1. 同步出口 `_get_completions`（AI 字段、服务器动作等一次性推理）：
   企业版实现是 `call_odoo_ai(env, "1/get_completions_sync", ...)`，直接改写它。
   返回值保持原契约：{'result': {'role': 'assistant', 'content': [part, ...]}}。

2. 聊天等 agentic 链路 `_save_and_submit_request`：
   企业版把 payload 发给远端 ai.api.odoo.com（会做 IAP 信用校验，没点数直接弹
   「信用不足」），本模块在 postcommit 后改走本地 GLM，再复用企业版自己的
   `_process_completion_result` 收尾（含工具轮次推进）。

消息/工具格式互转在 glm_client.py 里完成。
"""

import copy
import logging
import uuid

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.modules.registry import Registry

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

    def _save_and_submit_request(self, payload, *, callback_type,
                                 request_round, request_round_limit, state):
        """接管聊天 / 渠道命名等 agentic 请求的提交：不发 Odoo 远端，改走本地 GLM。

        企业版此方法在 postcommit 后把 payload 发给 ai.api.odoo.com（webhook 回调或
        同步 transport），两者都会做 IAP 信用校验（没点数就弹「信用不足」）。
        这里在 GLM 已配置时复刻其「写状态 -> postcommit -> 开新游标跑一轮 ->
        _process_completion_result」骨架，只把 LLM 调用换成我们的
        _get_completions（GLM）。后续轮次由
        _continue_agent_loop -> _advance_tool_batch -> _submit_agent_request
        再次进入本方法，靠游标 commit 触发 postcommit 逐轮推进——与企业版
        ai.use_webhook=False 分支的推进方式完全一致。
        """
        api_key, endpoint, model, enabled = get_client_config(self.env)
        if not (enabled and api_key):
            return super()._save_and_submit_request(
                payload,
                callback_type=callback_type,
                request_round=request_round,
                request_round_limit=request_round_limit,
                state=state,
            )

        self.ensure_one()
        guest = self.env.context.get("guest")
        payload = copy.deepcopy(payload)
        timeout = payload.pop('timeout', 120)
        vals = {
            "loop_state": "waiting_model",
            "request_uuid": str(uuid.uuid4()),
            "request_webhook_secret": uuid.uuid4().hex,
            "request_round": request_round,
            "request_round_limit": request_round_limit,
            "request_payload": payload,
            "request_user_id": self.env.uid,
            "request_guest_id": guest.id if guest else False,
            "request_context": self._get_request_context_snapshot(),
            "resume_token": False,
            "pending_tool_call": False,
        }
        state["callback_type"] = callback_type
        vals["state"] = state
        self.write(vals)
        self._publish_response_state()

        dbname = self.env.cr.dbname
        user_id = self.env.uid
        guest_id = vals["request_guest_id"]
        context = vals["request_context"]
        request_uuid = vals["request_uuid"]
        completion_options = {
            key: value for key, value in payload.items()
            if key not in ('messages', 'instructions', 'tools')
        }

        _logger.info('l_ai_glm 接管聊天请求：round=%s/%s, callback=%s, tools=%s',
                     request_round, request_round_limit, callback_type,
                     bool(payload.get('tools')))

        @self.env.cr.postcommit.add
        def submit():
            try:
                with Registry(dbname).cursor() as cr:
                    env = api.Environment(cr, user_id, context)
                    if guest_id:
                        env = env(context={**env.context, 'guest': env['mail.guest'].browse(guest_id)})
                    session = env['ai.session'].sudo().search([
                        ('request_uuid', '=', request_uuid),
                        ('loop_state', '=', 'waiting_model'),
                    ], limit=1)
                    if not session:
                        return
                    try:
                        result = session._get_completions(
                            payload.get('messages') or [],
                            payload.get('instructions') or '',
                            payload.get('tools'),
                            timeout=timeout,
                            **completion_options,
                        )
                    except Exception:
                        _logger.exception('l_ai_glm: GLM 聊天请求失败 (round=%s)', request_round)
                        session._finish_exchange(
                            'failed',
                            content=_('调用 GLM 失败，请查看服务器日志'),
                        )
                        return
                    env = session._get_completion_env()
                    # 与企业版 request.update_env() 一致：事务级工作也要恢复的 context
                    env.transaction.default_env = env
                    session.with_env(env)._process_completion_result(result)
            except Exception:
                _logger.exception('l_ai_glm: 本地 GLM 轮次执行失败 %s', request_uuid)
