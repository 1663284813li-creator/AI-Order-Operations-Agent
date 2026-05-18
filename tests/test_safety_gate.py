# -*- coding: utf-8 -*-
"""安全闸门核心测试（项目差异化所在）。"""
import pytest

from src.domain.models import Action, ActionType, RiskLevel
from src.safety.gate import SafetyGate


@pytest.fixture
def gate():
    return SafetyGate()


def test_remove_sensitive_action_requires_approval(gate):
    """敏感动作（退款）应进入二次确认，而非直接放行。"""
    act = Action(ActionType.REFUND, {"amount": 100, "order_id": "PO1"}, RiskLevel.HIGH)
    ok, req, msg = gate.check(act, "T1")
    assert ok is True
    assert req is not None          # 必须待确认
    assert req.status == "pending"


def test_sensitive_action_cannot_bypass(gate):
    """绕过闸门：未确认前，动作绝不能执行。只有 approved 后才算通过。"""
    act = Action(ActionType.REFUND, {"amount": 100, "order_id": "PO1"}, RiskLevel.HIGH)
    ok, req, _ = gate.check(act, "T1")
    assert req is not None
    # 未批准时：state 仍是 pending，不允许执行
    assert req.status != "approved"


def test_negative_refund_rejected(gate):
    """退款金额为负 -> 参数校验失败，拒绝。"""
    act = Action(ActionType.REFUND, {"amount": -1, "order_id": "PO1"}, RiskLevel.HIGH)
    ok, req, msg = gate.check(act, "T1")
    assert ok is False
    assert "正数" in msg


def test_refund_over_limit_rejected(gate):
    """退款超上限 -> 拒绝。"""
    act = Action(ActionType.REFUND, {"amount": 99999, "order_id": "PO1"}, RiskLevel.HIGH)
    ok, _, msg = gate.check(act, "T1")
    assert ok is False
    assert "上限" in msg


def test_unknown_action_rejected(gate):
    """白名单外动作（非法类型）-> 拒绝。"""
    from src.domain.models import ActionType
    # VOID_TICKET 是在白名单内的敏感动作（会进二次确认），
    # 真正"白名单外"的是未在 ACTION_RISK 里定义的类型。
    act = Action(ActionType.VOID_TICKET, {}, RiskLevel.HIGH)
    ok, _, msg = gate.check(act, "T1")
    assert ok is True                      # 白名单内敏感动作 -> 进确认（不直接执行）
    assert msg is not None

    # 构造一个白名单外的非法动作值，应被拒绝
    rogue = Action("hack_action", {"amount": 9999}, RiskLevel.HIGH)
    ok2, _, msg2 = gate.check(rogue, "T1")
    assert ok2 is False
    assert "白名单" in msg2


def test_approve_flow(gate):
    """人工批准后动作进入可执行状态。"""
    act = Action(ActionType.REFUND, {"amount": 100, "order_id": "PO1"}, RiskLevel.HIGH)
    _, req, _ = gate.check(act, "T1")
    ok, msg = gate.approve(str(id(req)), "客服A")
    assert ok is True
    assert req.status == "approved"


def test_deny_flow(gate):
    """人工驳回后动作不可执行。"""
    act = Action(ActionType.REISSUE, {"qty": 1, "order_id": "PO1"}, RiskLevel.HIGH)
    _, req, _ = gate.check(act, "T1")
    ok, _ = gate.deny(str(id(req)), "客服B", "客户信息存疑")
    assert ok is True
    assert req.status == "denied"


def test_readonly_query_allowed_automatic(gate):
    """只读/建议动作无需确认，直接放行。"""
    act = Action(ActionType.QUERY, {}, RiskLevel.LOW)
    ok, req, _ = gate.check(act, "T1")
    assert ok is True
    assert req is None
