# -*- coding: utf-8 -*-
"""入口：运行 Agent 处理一条工单诉求。

用法：
    python scripts/run.py                 # mock 模式（无 key 也能演示）
    python scripts/run.py --llm           # 真实 LLM 模式（需 .env 配置 key）
"""
import sys
from pathlib import Path

# 保证能 import src（脚本在 scripts/ 下运行时把项目根加入 sys.path）
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import create_agent  # noqa: E402
from src.config import settings  # noqa: E402


def main() -> None:
    use_llm = "--llm" in sys.argv
    print("=" * 60)
    print("企业级智能工单/售后运营 Agent")
    print(f"模型: {settings.model_name} | 已配置Key: {settings.has_model_key} | 模式: {'真实LLM' if use_llm else 'mock'}")
    print("=" * 60)

    user_input = input("请输入消费者诉求 (回车用示例): ").strip()
    if not user_input:
        user_input = "客户反馈上个月买的玻璃水少发了一瓶，要求补发。"

    agent = create_agent(mock=not use_llm, use_llm=use_llm)
    result = agent.run(user_input, customer="张三")

    print("\n--- Agent 回复 ---")
    print(result.get("answer", ""))
    print("\n--- 处理建议 ---")
    for s in result.get("suggestions", []):
        print(f"  摘要: {s.get('summary')}")
        for a in s.get("actions", []):
            print(f"    动作: {a['type']} | 风险: {a['risk']} | 需确认: {a['requires_approval']} | 参数: {a['params']}")
        for ap in s.get("pending_approvals", []):
            print(f"    [安全闸门] 待人工确认: {ap['action']} -> {ap['msg']}")
        if s.get("escalation_required"):
            print(f"    [升级人工] {s.get('escalation_reason')}")

    print("\n--- 运行指标 (Trace) ---")
    print(result.get("trace", {}))


if __name__ == "__main__":
    main()