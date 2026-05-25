# -*- coding: utf-8 -*-
"""真实 LLM 全链路演示：用户诉求 -> LLM 生成建议 -> 安全闸门 -> 人工确认。

用法：
    python scripts/demo_llm.py                       # 用默认示例
    python scripts/demo_llm.py "客户要退订单PO20260928-00002"  # 自定义诉求
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agent import create_agent  # noqa: E402
from src.evaluation.runner import EvalCase, EvalRunner, make_cases  # noqa: E402
from src.safety.gate import SafetyGate  # noqa: E402
from src.domain.models import Action, ActionType  # noqa: E402
from src.tools import llm_suggestion  # noqa: E402
from src.domain.models import Ticket  # noqa: E402

user_input = sys.argv[1] if len(sys.argv) > 1 else "客户反映订单 PO20260928-00001 少发了一瓶玻璃水，要求补发。"

print("=" * 66)
print("真实 LLM 全链路演示")
print("=" * 66)
agent = create_agent(use_llm=True)   # 强制真实 LLM
print(f"模式: 真实LLM | 模型: {agent.llm.model}\n")

result = agent.run(user_input, customer="张三")

print("--- Agent 回复 ---")
print(result.get("answer", "(无)") or "(无)")
print("\n--- 处理建议 ---")
for s in result.get("suggestions", []):
    print(f"■ 摘要: {s.get('summary')}")
    for a in s.get("actions", []):
        print(f"  动作: {a['type']} | 风险: {a['risk']} | 需确认: {a['requires_approval']} | 参数: {a['params']}")
    for ap in s.get("pending_approvals", []):
        print(f"  🔒 [安全闸门] 待人工确认 #{ap['id']}: {ap['action']} -> {ap['msg']}")
    if s.get("escalation_required"):
        print(f"  ⚠️ [升级人工] {s.get('escalation_reason')}")

print("\n--- 运行指标 (Trace) ---")
print(result.get("trace", {}))

# 强制展示：即使 LLM 输出敏感动作，闸门也能拦
print("\n" + "=" * 66)
print("安全验证：敏感动作（退款）在真实链路上同样被闸门拦截")
print("=" * 66)
gate = SafetyGate()
act = Action(ActionType.REFUND, {"amount": 458.0, "order_id": "PO20260928-00002"}, "high")
ok, req, msg = gate.check(act, "DEMO-TICKET")
print(f"check(退款458元): 放行={ok} 待确认={req is not None}")
assert req is not None and req.status == "pending"
print("✅ 退款必须人工二次确认，未确认前不可执行")

print("\n=== 验证完成 ===")