# -*- coding: utf-8 -*-
"""记忆落数据演示：会话记忆 + 跨会话用户画像。

用法：python scripts/demo_memory.py [--llm]
- 默认 mock 模式（无需 key，快速验证记忆链路）
- --llm 用真实模型（可看到画像注入对回复的影响）

演示内容：
1. 客户张三第一次工单 -> 画像记录门店/商品/问题类型
2. 再次找 Agent -> 画像摘要注入上下文（"该客户常处理..."）
3. 客户李四 -> 画像隔离（不会串人）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agent import create_agent  # noqa: E402
from src.memory.store import session_memory, user_profile  # noqa: E402


def show_profile(customer: str):
    print(f"  [画像] {customer}: {user_profile.summary_for(customer) or '(空)'}")


def main() -> None:
    use_llm = "--llm" in sys.argv
    session_memory.clear()
    user_profile.clear()

    agent = create_agent(mock=not use_llm, use_llm=use_llm)
    mode = "真实 LLM" if use_llm else "mock"
    print("=" * 66)
    print(f"记忆演示（{mode} 模式）")
    print("=" * 66)

    print("\n--- 第 1 次工单：张三（少发补发） ---")
    out1 = agent.run("客户张三反映订单 PO20260928-00001 少发了一瓶玻璃水，要求补发。", customer="张三")
    show_profile("张三")
    print(f"  会话历史条数: {len(session_memory.messages())}")

    print("\n--- 第 2 次工单：张三（换商品查库存） ---")
    out2 = agent.run("客户张三想查订单 PO20260928-00002 的物流进度。", customer="张三")
    show_profile("张三")
    print(f"  会话历史条数: {len(session_memory.messages())}")
    print(f"  会话摘要: {session_memory.summarize()[:150]}")

    print("\n--- 第 3 次工单：李四（新客户） ---")
    out3 = agent.run("客户李四买的行车记录仪坏了要退款。", customer="李四")
    show_profile("李四")
    show_profile("张三")   # 张三画像不受影响
    print(f"  会话历史条数: {len(session_memory.messages())}")

    print("\n" + "=" * 66)
    print("记忆链路验证")
    print("=" * 66)
    zhang = user_profile.get("张三")
    li = user_profile.get("李四")
    assert zhang["last_store"] == "苏州工业园店", "张三画像应记录门店"
    assert "李四" in user_profile._profiles and zhang is not None
    print(f"✅ 张三画像: 门店计数 {zhang['store_counter']} | SKU计数 {zhang['sku_counter']} | 问题计数 {zhang['issue_counter']}")
    print(f"✅ 李四画像: {li['last_issue'] if li else '(空)'}")
    print(f"✅ 会话记忆: {len(session_memory.messages())} 条（TTL={session_memory.ttl}s, 上限={session_memory.max_entries}）")
    print("\n记忆演示通过 ✅")


if __name__ == "__main__":
    main()