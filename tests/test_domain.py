# -*- coding: utf-8 -*-
"""领域模型与动作风险映射测试。"""
from src.domain.models import ACTION_RISK, ActionType, RiskLevel


def test_action_risk_mapping():
    """敏感动作应标记为 HIGH。"""
    assert ACTION_RISK[ActionType.REFUND] == RiskLevel.HIGH
    assert ACTION_RISK[ActionType.REISSUE] == RiskLevel.HIGH
    assert ACTION_RISK[ActionType.MODIFY_ORDER] == RiskLevel.HIGH
    assert ACTION_RISK[ActionType.VOID_TICKET] == RiskLevel.HIGH


def test_readonly_low_risk():
    assert ACTION_RISK[ActionType.QUERY] == RiskLevel.LOW
    assert ACTION_RISK[ActionType.SUGGEST] == RiskLevel.LOW
