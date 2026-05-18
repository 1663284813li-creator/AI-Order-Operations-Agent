# -*- coding: utf-8 -*-
"""Agent 冒烟：mock 模式跑通全流程。"""
from src.agent import create_agent


def test_mock_agent_run():
    """无 key 时 mock 模式应能产出建议 + 敏感动作待确认。"""
    agent = create_agent(mock=True)
    out = agent.run("客户反馈上个月买的玻璃水少发了一瓶，要求补发。", customer="张三")
    assert out["answer"]
    assert "suggestions" in out