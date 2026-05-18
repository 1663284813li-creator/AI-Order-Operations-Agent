# -*- coding: utf-8 -*-
"""领域模型。

这些 dataclass 定义整个系统的核心数据结构：
- Order:  一笔订单（查询用）
- Ticket: 一条售后/工单（问题载体）
- Action: 一个待执行动作（含风险等级，安全闸门据此拦截）
- Suggestion: Agent 给出的处理建议
- AuditRecord: 留痕记录（谁批的、何时、依据）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActionType(str, Enum):
    """敏感/普通动作类型。"""

    QUERY = "query"                  # 只读查询
    SUGGEST = "suggest"              # 给建议
    REFUND = "refund"                # 退款（敏感）
    REISSUE = "reissue"              # 补发（敏感）
    MODIFY_ORDER = "modify_order"    # 改单（敏感）
    VOID_TICKET = "void_ticket"      # 作废工单（敏感）
    ESCALATE = "escalate"            # 升级人工


class RiskLevel(str, Enum):
    """动作风险等级，决定是否需要人工确认。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"          # 必须人工二次确认


# 敏感动作 -> 风险等级 映射（代码级硬编码，不依赖 LLM）
ACTION_RISK: dict[ActionType, RiskLevel] = {
    ActionType.QUERY: RiskLevel.LOW,
    ActionType.SUGGEST: RiskLevel.LOW,
    ActionType.REFUND: RiskLevel.HIGH,
    ActionType.REISSUE: RiskLevel.HIGH,
    ActionType.MODIFY_ORDER: RiskLevel.HIGH,
    ActionType.VOID_TICKET: RiskLevel.HIGH,
    ActionType.ESCALATE: RiskLevel.MEDIUM,
}


@dataclass
class Order:
    """一笔订单。"""

    order_id: str
    customer: str
    store: str
    amount: float
    status: str
    items: list[dict] = field(default_factory=list)   # [{sku, name, qty, price}]
    created_at: str = ""


@dataclass
class Ticket:
    """一条售后/工单。"""

    ticket_id: str
    customer: str                     # 消费者（服务对象）
    store: str                        # 所属门店
    issue_type: str                   # 少发/错发/破损/退款/投诉...
    description: str                  # 问题描述
    related_order_id: Optional[str] = None
    status: str = "open"              # open / processing / resolved / escalated
    created_at: str = ""


@dataclass
class Action:
    """一个待执行/已执行动作。"""

    type: ActionType
    params: dict                      # 如 {"amount": 458, "qty": 1, "order_id": "..."}
    risk: RiskLevel
    reason: str = ""                  # 为什么这样处理（留痕用）
    requires_approval: bool = False
    approved_by: Optional[str] = None   # 人工确认者


@dataclass
class Suggestion:
    """Agent 给出的处理建议（仅供展示，不执行）。"""

    summary: str
    actions: list[Action] = field(default_factory=list)
    escalation_required: bool = False
    escalation_reason: str = ""


@dataclass
class AuditRecord:
    """留痕记录。"""

    ticket_id: str
    action: Action
    operator: str                     # 自动 / 人工ID
    decision: str                     # allowed / denied / escalated
    timestamp: str
    note: str = ""
