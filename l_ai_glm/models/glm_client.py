# -*- coding: utf-8 -*-
"""智谱 GLM 的 OpenAI 兼容客户端 + Odoo 消息格式互转。

Odoo 20 内部用的消息结构是"AIMessageParts"：一条消息 = {"role": ..., "content": [part...]}，
part 有四种：
    {'type': 'text',        'text': str}
    {'type': 'inline_data', 'data': Any, 'mimetype': str}
    {'type': 'tool_call',   'name': str, 'args': dict, 'call_id': Any}
    {'type': 'tool_result', 'tool_name': str, 'tool_call_id': str,
     'result': [part...], 'success': bool}
OpenAI 侧是标准 messages + tool_calls / role=tool，下面两个函数负责互转。
"""

import json
import logging

import requests

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = 'https://open.bigmodel.cn/api/paas/v4'
DEFAULT_MODEL = 'glm-4.6'


class GLMError(Exception):
    """调用 GLM 失败。"""


def get_client_config(env):
    """读取配置。返回 (api_key, endpoint, model, enabled)。"""
    params = env['ir.config_parameter'].sudo()
    return (
        (params.get_str('l_ai_glm.api_key') or '').strip(),
        (params.get_str('l_ai_glm.endpoint') or '').strip() or DEFAULT_ENDPOINT,
        (params.get_str('l_ai_glm.model') or '').strip() or DEFAULT_MODEL,
        bool(params.get_int('l_ai_glm.enabled') or 1),
    )


def parts_to_text(parts):
    """把 AIMessageParts 拼成纯文本（只取 text 部分，与上游 get_text_from_parts 同语义）。"""
    if isinstance(parts, str):
        return parts
    texts = []
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        if part.get('type') == 'text' and part.get('text'):
            texts.append(part['text'])
        elif part.get('type') == 'tool_result':
            texts.append(parts_to_text(part.get('result')))
    return '\n'.join(texts)


def _normalize_tools(tools):
    """Odoo 传进来的 tools 可能是 list，也可能是 {'tools': [...]}（不同版本写法不一）。"""
    if not tools:
        return []
    if isinstance(tools, dict):
        tools = tools.get('tools') or []
    return [t for t in tools if isinstance(t, dict) and t.get('name')]


def build_openai_tools(tools):
    """[{name, instructions, schema}] -> OpenAI tools 数组。"""
    result = []
    for tool in _normalize_tools(tools):
        result.append({
            'type': 'function',
            'function': {
                'name': tool['name'],
                'description': tool.get('instructions') or '',
                'parameters': tool.get('schema') or {
                    'type': 'object',
                    'properties': {},
                    'required': [],
                },
            },
        })
    return result


def build_openai_messages(messages, instructions):
    """Odoo messages -> OpenAI messages。"""
    result = []
    if instructions:
        result.append({'role': 'system', 'content': instructions})

    for message in messages or []:
        role = message.get('role')
        parts = message.get('content') or []

        if role == 'user':
            text_chunks, image_urls, tool_results = [], [], []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                ptype = part.get('type')
                if ptype == 'text':
                    if part.get('text'):
                        text_chunks.append(part['text'])
                elif ptype == 'inline_data':
                    data = part.get('data')
                    if data:
                        mimetype = part.get('mimetype') or 'image/png'
                        image_urls.append(f'data:{mimetype};base64,{data}')
                elif ptype == 'tool_result':
                    tool_results.append(part)

            content = []
            if text_chunks:
                content.append({'type': 'text', 'text': '\n'.join(text_chunks)})
            for url in image_urls:
                content.append({'type': 'image_url', 'image_url': {'url': url}})
            if content:
                result.append({'role': 'user', 'content': content})

            # 工具结果必须是独立的 role=tool 消息
            for tool_result in tool_results:
                result.append({
                    'role': 'tool',
                    'tool_call_id': str(tool_result.get('tool_call_id') or ''),
                    'content': parts_to_text(tool_result.get('result')),
                })

        elif role == 'assistant':
            text_chunks, tool_calls = [], []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                if part.get('type') == 'text':
                    if part.get('text'):
                        text_chunks.append(part['text'])
                elif part.get('type') == 'tool_call':
                    tool_calls.append({
                        'id': str(part.get('call_id') or ''),
                        'type': 'function',
                        'function': {
                            'name': part.get('name') or '',
                            'arguments': json.dumps(part.get('args') or {}, ensure_ascii=False),
                        },
                    })
            msg = {'role': 'assistant', 'content': '\n'.join(text_chunks)}
            if tool_calls:
                msg['tool_calls'] = tool_calls
            result.append(msg)

    return result


def build_openai_payload(messages, instructions, tools, **options):
    """组装 chat/completions 请求体。

    Odoo 的 CompletionOptions 里我们实际能落到 GLM 上的：
      schema           -> response_format = json_object（GLM 保证输出合法 JSON）
      boost_reasoning  -> GLM 的思考模式
      web_grounding / aspect_ratio / usage / image_generation -> 不支持，跳过
    """
    payload = {
        'messages': build_openai_messages(messages, instructions),
        'stream': False,
    }
    if openai_tools := build_openai_tools(tools):
        payload['tools'] = openai_tools
        payload['tool_choice'] = 'auto'

    if options.get('schema'):
        payload['response_format'] = {'type': 'json_object'}
    if options.get('boost_reasoning'):
        payload['thinking'] = {'type': 'enabled'}

    return payload


def call_glm(env, api_key, endpoint, model, messages, instructions, tools, timeout=60, **options):
    """发一次非流式请求，返回 GLM 的原始 assistant message dict。"""
    url = f"{endpoint.rstrip('/')}/chat/completions"
    payload = build_openai_payload(messages, instructions, tools, **options)
    payload['model'] = model

    _logger.debug('GLM request: %s', json.dumps(payload, ensure_ascii=False)[:2000])
    try:
        response = requests.post(
            url,
            json=payload,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            timeout=timeout or 60,
        )
    except requests.exceptions.RequestException as err:
        raise GLMError(_('无法连接 GLM 服务：%s', err)) from err

    if response.status_code != 200:
        raise GLMError(
            _('GLM 返回 HTTP %(code)s：%(body)s',
              code=response.status_code,
              body=response.text[:500])
        )

    try:
        data = response.json()
    except ValueError as err:
        raise GLMError(_('GLM 返回了非 JSON 内容：%s', response.text[:300])) from err

    if error := data.get('error'):
        raise GLMError(_('GLM 接口报错：%s', error.get('message') or error))

    choices = data.get('choices') or []
    if not choices:
        raise GLMError(_('GLM 没有返回任何结果：%s', str(data)[:300]))
    return choices[0].get('message') or {}


def glm_message_to_parts(glm_message):
    """GLM assistant message -> Odoo parts 列表。"""
    parts = []
    if text := (glm_message.get('content') or '').strip():
        parts.append({'type': 'text', 'text': text})

    for tool_call in glm_message.get('tool_calls') or []:
        function = tool_call.get('function') or {}
        raw_args = function.get('arguments') or '{}'
        try:
            args = json.loads(raw_args)
        except ValueError:
            _logger.warning('GLM 返回的工具参数不是合法 JSON: %s', raw_args)
            args = {}
        parts.append({
            'type': 'tool_call',
            'name': function.get('name') or '',
            'args': args,
            'call_id': tool_call.get('id') or '',
        })

    # 既没文本也没工具调用时补一个空文本，避免上层拿不到任何 part
    if not parts:
        parts.append({'type': 'text', 'text': ''})
    return parts
