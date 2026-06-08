# -*- coding: utf-8 -*-
"""记忆层测试：会话记忆 + 用户画像落数据。"""
from src.memory.store import SessionMemory, UserProfileMemory


def test_session_memory_ttl_and_window():
    m = SessionMemory(ttl=3600, max_entries=3)
    for i in range(5):
        m.add("user", f"msg-{i}")
    msgs = m.messages()
    assert len(msgs) == 3          # 滑动窗口
    assert msgs[0]["content"] == "msg-2"
    assert msgs[-1]["content"] == "msg-4"
    assert m.summarize()           # 摘要非空


def test_session_memory_clear():
    m = SessionMemory()
    m.add("user", "hi")
    m.clear()
    assert m.messages() == []


def test_profile_record_and_summary():
    p = UserProfileMemory()
    p.record_order("张三", "苏州工业园店", "CC-BLS001", "少发")
    p.record_order("张三", "苏州工业园店", "CC-BLS001", "少发")
    p.record_order("张三", "北京朝阳店", "XC-JLY008", "退款")
    prof = p.get("张三")
    assert prof["store_counter"]["苏州工业园店"] == 2
    assert prof["sku_counter"]["CC-BLS001"] == 2
    s = p.summary_for("张三")
    assert "苏州工业园店" in s
    assert len(s) <= 200


def test_profile_empty_user():
    p = UserProfileMemory()
    assert p.summary_for("不存在的人") == ""
    assert p.get("不存在的人") == {}