# -*- coding: utf-8 -*-
"""业务工具实现（数据源版）。

这一层是 Agent 的"手"——每个工具做一件事，返回结构化数据。
查询类工具全部走 data_source（极客云模拟数据），不再用硬编码 mock。

- query_order:      按订单号查订单（只读，含多 SKU 明细聚合）
- query_logistics:  查物流（只读）
- check_inventory:  查门店库存（只读，为库存闸门准备）
- create_suggestion: 生成处理建议（不执行；MVP 为规则版，LLM 版见 llm_suggestion）
- escalate_ticket:  升级人工（安全动作，需确认流程）

敏感动作（退款/补发/改单/作废）由 safety 层单独注册，见 safety.gate。
"""
from __future__ import annotations

from typing import Any

from src.data_source import data_source
from src.domain.models import Action, ActionType, RiskLevel, Suggestion, Ticket
from src.logger import log


# ----------------------------------------------------------------------
# 查询类工具（走数据源）
# ----------------------------------------------------------------------
def query_order(order_id: str) -> dict[str, Any]:
    """按订单号查订单（只读）。

    数据源为极客云订单导出（一单多 SKU 明细，已聚合）。
    脏数据行（空订单号/空商品/负数数量）在数据源加载时已剔除。
    """
    log.info("query_order: %s", order_id)
    order = data_source.get_order(order_id)
    if order is None:
        return {"success": False, "reason": f"订单 {order_id} 不存在或已被清洗（含脏数据）"}
    return {"success": True, "order": {
        "order_id": order.order_id,
        "customer": order.customer,
        "store": order.store,
        "amount": order.amount,
        "status": order.status,
        "created_at": order.created_at,
        "items": order.items,
    }}


def query_logistics(order_id: str) -> dict[str, Any]:
    """查物流（只读）。"""
    log.info("query_logistics: %s", order_id)
    lr = data_source.get_logistics(order_id)
    if lr is None:
        return {"success": False, "reason": f"订单 {order_id} 无物流信息"}
    return {"success": True, "logistics": lr}


def check_inventory(store: str, sku: str) -> dict[str, Any]:
    """查门店可用库存（只读，库存闸门用）。"""
    log.info("check_inventory: %s/%s", store, sku)
    inv = data_source.get_inventory(store, sku)
    if inv is None:
        return {"success": False, "reason": f"门店 {store} 无商品 {sku} 库存记录"}
    return {
        "success": True,
        "store": store,
        "sku": sku,
        "total_qty": inv["qty"],
        "available_qty": inv["available"],
        "safety_qty": inv["safety"],
    }


# ----------------------------------------------------------------------
# 建议/升级工具
# ----------------------------------------------------------------------
def create_suggestion(ticket: Ticket, reasoning: str, use_llm: bool = False,
                      llm=None) -> Suggestion:
    """生成处理建议（仅供展示，不执行）。

    - use_llm=False（默认）：规则版，MVP 按问题类型给默认建议；
    - use_llm=True：走 LLM 版生成器（见 tools/llm_suggestion.py），
      失败时自动回退规则版，保证可用性。
    """
    if use_llm:
        try:
            from src.tools.llm_suggestion import generate as llm_suggestion

            sug = llm_suggestion(ticket, llm=llm)
            if sug is not None:
                return sug
            log.warning("LLM 建议生成失败，回退规则版")
        except Exception as e:
            log.warning("LLM 建议生成异常(%s)，回退规则版", e)

    actions: list[Action] = []
    if ticket.issue_type in ("少发", "漏发"):
        actions.append(
            Action(
                type=ActionType.REISSUE,
                params={"qty": 1, "order_id": ticket.related_order_id},
                risk=RiskLevel.HIGH,
                reason=reasoning,
                requires_approval=True,
            )
        )
    elif ticket.issue_type == "退款":
        actions.append(
            Action(
                type=ActionType.REFUND,
                params={"amount": 199.0, "order_id": ticket.related_order_id},
                risk=RiskLevel.HIGH,
                reason=reasoning,
                requires_approval=True,
            )
        )
    return Suggestion(summary=reasoning, actions=actions)


def escalate_ticket(ticket_id: str, reason: str) -> dict[str, Any]:
    """升级人工（安全动作，需确认流程）。"""
    log.info("escalate_ticket: %s, reason=%s", ticket_id, reason)
    return {"success": True, "ticket_id": ticket_id, "escalated": True, "reason": reason}