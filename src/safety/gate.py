# -*- coding: utf-8 -*-
"""安全闸门 —— 本项目的核心差异化。

原则（与立项方案第 6 节一致）：
1. 敏感动作白名单：只有代码显式允许的动作才能执行。
2. 参数校验：金额/数量/订单号做格式与范围校验。
3. 二次确认：HIGH 风险动作必须人工确认后才能真实执行。
4. 失败默认拒绝：任何校验异常/超时/信息缺失 → 拒绝并升级人工。

关键：安全不依赖大模型自觉，全部由代码强制。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from src.config import settings
from src.domain.models import ACTION_RISK, Action, ActionType, AuditRecord, RiskLevel
from src.logger import log

# 危险操作名单（非白名单动作一律拒绝）
_SAFE_AUTO_ACTIONS = {ActionType.QUERY, ActionType.SUGGEST, ActionType.ESCALATE}
# 敏感动作（HIGH）必须人工确认
_SENSITIVE_ACTIONS = {t for t, r in ACTION_RISK.items() if r == RiskLevel.HIGH}


@dataclass
class ApprovalRequest:
    """二次确认请求：敏感动作生成后进入待确认队列。"""

    action: Action
    ticket_id: str
    reason: str = ""
    status: str = "pending"          # pending / approved / denied
    note: str = ""


class SafetyGate:
    """安全闸门：统一校验 + 二次确认管理。"""

    def __init__(self) -> None:
        self._pending: list[ApprovalRequest] = []
        self._audit: list[AuditRecord] = []

    # ------------------------------------------------------------------
    # 动作白名单
    # ------------------------------------------------------------------
    def is_action_allowed(self, action: Action) -> bool:
        """动作是否在白名单自动处理范围内（不含敏感动作）。"""
        return action.type in _SAFE_AUTO_ACTIONS

    # ------------------------------------------------------------------
    # 参数校验
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_params(p: dict) -> dict:
        """参数规范化：统一 LLM 可能输出的字段别名。

        作用：即使 LLM 输出 quantity/count/money 等别名，安全闸门也能用标准
        字段（qty/amount/order_id）做校验，避免"参数名不一致导致校验失效"。
        """
        if not isinstance(p, dict):
            return {}
        mapping = {
            "quantity": "qty",
            "count": "qty",
            "num": "qty",
            "number": "qty",
            "money": "amount",
            "price": "amount",
            "refund_amount": "amount",
            "total": "amount",
            "orderid": "order_id",
            "order_no": "order_id",
            "orderno": "order_id",
            "order": "order_id",
            "product_code": "sku",
            "store_name": "store",
        }
        out = dict(p)
        for alias, canonical in mapping.items():
            if alias in out and canonical not in out:
                out[canonical] = out[alias]
        return out

    def validate(self, action: Action) -> tuple[bool, str]:
        """参数合法性校验。失败默认拒绝。"""
        p = self._normalize_params(action.params or {})

        # 退款金额
        if action.type == ActionType.REFUND:
            amount = p.get("amount")
            if amount is None:
                return False, "退款金额缺失"
            if not isinstance(amount, (int, float)) or isinstance(amount, bool):
                return False, "退款金额格式错误"
            if amount <= 0:
                return False, "退款金额必须为正数"
            if amount > settings.refund_max_amount:
                return False, f"退款金额超过上限 {settings.refund_max_amount}，需人工介入"

        # 补发数量
        if action.type == ActionType.REISSUE:
            qty = p.get("qty")
            if qty is None:
                return False, "补发数量缺失"
            if not isinstance(qty, (int, float)) or isinstance(qty, bool):
                return False, "补发数量格式错误"
            if qty <= 0:
                return False, "补发数量必须为正数"
            if qty > settings.reissue_max_qty:
                return False, f"补发数量超过上限 {settings.reissue_max_qty}，需人工介入"

        # 订单号必填
        if action.type in (ActionType.REFUND, ActionType.REISSUE, ActionType.MODIFY_ORDER):
            order_id = p.get("order_id")
            if not order_id or not str(order_id).strip():
                return False, "订单号不能为空"

        return True, "ok"

    # ------------------------------------------------------------------
    # 核心执行流程
    # ------------------------------------------------------------------
    def check(self, action: Action, ticket_id: str) -> tuple[bool, Optional[ApprovalRequest], str]:
        """对动作做完整安全校验。

        返回 (是否放行, 待确认请求, 说明)。
        - 放行=True 且 approval 非空：动作进入二次确认等待（还不能执行）。
        - 放行=True 且 approval 为空：动作可直接执行（只读/建议）。
        - 放行=False：动作被拒绝，reason 说明原因。
        """
        # 1) 动作类型合法性
        if not action.type:
            return False, None, "动作类型为空，拒绝执行"

        # 2) 白名单
        if action.type not in ACTION_RISK:
            return False, None, f"动作 {action.type} 不在白名单，拒绝执行"

        # 3) 参数校验
        ok, msg = self.validate(action)
        if not ok:
            return False, None, f"参数校验失败：{msg}"

        # 4) 敏感动作 → 二次确认
        if action.type in _SENSITIVE_ACTIONS:
            req = ApprovalRequest(action=action, ticket_id=ticket_id, reason=action.reason)
            self._pending.append(req)
            log.info("敏感动作进入二次确认: %s ticket=%s", action.type, ticket_id)
            return True, req, "动作已进入人工二次确认，等待审批"

        # 5) 普通可执行动作
        return True, None, "动作通过校验，可执行"

    # ------------------------------------------------------------------
    # 二次确认管理（人工操作）
    # ------------------------------------------------------------------
    def list_pending(self) -> list[ApprovalRequest]:
        return [r for r in self._pending if r.status == "pending"]

    def approve(self, req_id: str, operator: str) -> tuple[bool, str]:
        """人工批准敏感动作执行。"""
        for r in self._pending:
            if id(r) == int(req_id) and r.status == "pending":
                r.status = "approved"
                r.note = f"批准人: {operator}"
                self._audit.append(
                    AuditRecord(
                        ticket_id=r.ticket_id,
                        action=r.action,
                        operator=operator,
                        decision="approved",
                        timestamp=_now(),
                        note="人工二次确认通过",
                    )
                )
                log.info("人工批准: %s by %s", r.action.type, operator)
                return True, "已批准"
        return False, "确认请求不存在或已处理"

    def deny(self, req_id: str, operator: str, reason: str) -> tuple[bool, str]:
        """人工驳回敏感动作。"""
        for r in self._pending:
            if id(r) == int(req_id) and r.status == "pending":
                r.status = "denied"
                r.note = f"驳回人: {operator}, 原因: {reason}"
                self._audit.append(
                    AuditRecord(
                        ticket_id=r.ticket_id,
                        action=r.action,
                        operator=operator,
                        decision="denied",
                        timestamp=_now(),
                        note=f"人工驳回: {reason}",
                    )
                )
                log.info("人工驳回: %s by %s reason=%s", r.action.type, operator, reason)
                return True, "已驳回"
        return False, "确认请求不存在或已处理"

    # ------------------------------------------------------------------
    def audit_log(self) -> list[AuditRecord]:
        return list(self._audit)

    # ------------------------------------------------------------------
    # 序列化（供界面/导出/评测使用）
    # ------------------------------------------------------------------
    def pending_dicts(self) -> list[dict]:
        """待确认请求 -> 可序列化 dict（含稳定编号）。"""
        return [
            {
                "id": id(r),
                "action": r.action.type.value,
                "params": r.action.params,
                "risk": r.action.risk.value,
                "ticket_id": r.ticket_id,
                "reason": r.reason,
                "status": r.status,
            }
            for r in self._pending
            if r.status == "pending"
        ]

    def audit_dicts(self) -> list[dict]:
        """审计留痕 -> 可序列化 dict 列表（导出 JSON/CSV 用）。"""
        return [
            {
                "ticket_id": r.ticket_id,
                "action": r.action.type.value,
                "params": json.dumps(r.action.params, ensure_ascii=False),
                "operator": r.operator,
                "decision": r.decision,
                "timestamp": r.timestamp,
                "note": r.note,
            }
            for r in self._audit
        ]


def _now() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# 全局唯一闸门实例（MVP 用单实例；生产可换 Redis 持久化）
safety_gate = SafetyGate()