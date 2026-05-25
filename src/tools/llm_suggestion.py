# -*- coding: utf-8 -*-
"""LLM 建议生成器：用真实模型生成处理建议（结构化 JSON 输出）。

设计要点：
1. 模型只负责"建议"，不负责"执行"——输出动作必须经过白名单校验，
   敏感动作（退款/补发等）一律标记 requires_approval，由安全闸门兜底。
2. 强制 JSON 输出 + 字段校验：解析失败或动作非法时返回 None，
   由业务层自动回退规则版，保证可用性（fail-safe）。
3. 复用 LLMClient（多模型 OpenAI 兼容），换模型只改 .env。
"""
from __future__ import annotations

import json
import re
from typing import Optional

from src.domain.models import Action, Suggestion, Ticket, RiskLevel, ActionType, ACTION_RISK
from src.logger import log

SYSTEM_PROMPT = """你是一个企业级工单/售后运营 Agent 的处理建议生成器。
根据消费者报障信息，输出**唯一一个 JSON 对象**，不要输出任何其他内容。

JSON 结构：
{
  "summary": "一句话总结问题与处理思路",
  "actions": [
    {
      "type": "动作类型，只能从枚举中选择",
      "params": {"金额/数量/订单号等参数"},
      "reason": "为什么这么处理"
    }
  ],
  "escalation_required": false,
  "escalation_reason": "如需升级人工，说明原因（否则为空字符串）"
}

动作类型枚举（只能选这些）：
- query        只读查询
- suggest      仅建议
- refund       退款（敏感，系统会自动要求人工确认）
- reissue      补发（敏感，系统会自动要求人工确认）
- modify_order 修改订单（敏感，系统会自动要求人工确认）
- escalate     升级人工

参数规则：
- 金额字段名用 amount（单位元）、数量字段名用 qty、订单号用 order_id。
- **reissue（补发）必须带 sku 字段**（商品编码，从订单明细里选），可选带 store（门店）；
  若订单含多个商品而诉求不明确，宁可 escalation_required=true，也不要乱猜 sku。
- 敏感动作（refund/reissue/modify_order）不要写执行理由，系统会自动拦截并转人工。
- 信息不足、诉求超规则、客户情绪激烈时，escalation_required 设为 true。
- params 里的金额/数量必须是数字。
"""


def _parse_llm_json(text: str) -> Optional[dict]:
    """鲁棒解析 LLM 输出的 JSON（容忍 ```json 包裹等）。"""
    if not text:
        return None
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _validate_actions(raw_actions: list) -> list[Action]:
    """校验/清洗 LLM 输出的动作。

    只保留白名单内的动作类型；参数做基本类型清洗。
    白名单外动作一律丢弃（防幻觉/注入）。
    """
    actions: list[Action] = []
    for raw in raw_actions[:5]:  # 单条建议最多 5 个动作
        if not isinstance(raw, dict):
            continue
        try:
            atype = ActionType(str(raw.get("type", "")).strip().lower())
        except ValueError:
            log.warning("LLM 输出白名单外动作类型: %s，已丢弃", raw.get("type"))
            continue
        if atype not in ACTION_RISK:
            continue

        params = raw.get("params") or {}
        if not isinstance(params, dict):
            params = {}

        # 源头参数规范化：quantity/count -> qty, money -> amount 等
        # 与 SafetyGate._normalize_params 一致，保证动作参数名统一、校验不失效
        from src.safety.gate import SafetyGate

        params = SafetyGate._normalize_params(params)

        actions.append(
            Action(
                type=atype,
                params=params,
                risk=ACTION_RISK[atype],
                reason=str(raw.get("reason", "") or "")[:200],  # 防超长
                requires_approval=ACTION_RISK[atype] == RiskLevel.HIGH,
            )
        )
    return actions


def generate(ticket: Ticket, llm=None) -> Optional[Suggestion]:
    """用 LLM 生成处理建议；失败/非法时返回 None（由调用方回退）。"""
    from src.models.client import LLMClient
    from src.data_source import data_source

    llm = llm or LLMClient()

    # 查询关联订单明细，注入 prompt，让 LLM 能依据真实商品/门店精确决策
    order_detail = ""
    order = data_source.get_order(ticket.related_order_id) if ticket.related_order_id else None
    if order:
        lines = "\n".join(
            f"  - SKU {it['sku']} | {it['name']} | 规格 {it['spec']} | 单价 {it['price']} | 数量 {it['qty']}"
            for it in order.items
        )
        order_detail = (
            f"【订单明细】订单 {order.order_id}，门店 {order.store}，状态 {order.status}，金额 {order.amount}\n"
            f"{lines}\n"
        )

    user_prompt = (
        f"【工单信息】\n"
        f"- 工单号: {ticket.ticket_id}\n"
        f"- 消费者: {ticket.customer}\n"
        f"- 门店: {ticket.store}\n"
        f"- 问题类型: {ticket.issue_type}\n"
        f"- 关联订单: {ticket.related_order_id or '未知'}\n"
        f"- 问题描述: {ticket.description}\n\n"
        f"{order_detail}"
        f"请给出处理建议（JSON）。补发(reissue)必须带 sku（从订单明细里选）。"
    )

    try:
        content = llm.chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
    except Exception as e:
        log.warning("LLM 调用失败: %s", e)
        return None

    obj = _parse_llm_json(content)
    if obj is None:
        log.warning("LLM 输出无法解析为 JSON，回退规则版")
        return None

    actions = _validate_actions(obj.get("actions") or [])
    escalation = bool(obj.get("escalation_required"))
    return Suggestion(
        summary=str(obj.get("summary", ""))[:300],
        actions=actions,
        escalation_required=escalation,
        escalation_reason=str(obj.get("escalation_reason", ""))[:200],
    )