# -*- coding: utf-8 -*-
"""冒烟：数据源 + Agent 完整流程（mock 模式，不依赖 API key）。

覆盖：
1. 数据源加载（极客云 CSV -> 内存索引）与脏数据清洗
2. query_order / query_logistics / check_inventory 真实查询
3. Agent mock 全流程（真实订单 + 安全闸门拦截 + 建议）
4. LLM 建议生成器的"解析/校验"部分（不调 API）：JSON 解析 + 白名单清洗
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agent import create_agent  # noqa: E402
from src.data_source import DataSource  # noqa: E402
from src.domain.models import Action, ActionType  # noqa: E402
from src.safety.gate import SafetyGate  # noqa: E402
from src.tools import llm_suggestion  # noqa: E402

print("=" * 60)
print("冒烟 1：数据源加载（极客云模拟数据）")
print("=" * 60)
ds = DataSource()
ds.load()
stats = ds.dirty_stats()
print(f"数据源加载完成：清洗脏数据行: {stats['orders_dirty_rows_removed']}")
all_orders = ds.all_orders()
print(f"可用订单数: {len(all_orders)}")
demo = all_orders[0]
print(f"示例订单: {demo.order_id} | 客户: {demo.customer} | 门店: {demo.store} | 金额: {demo.amount} | 明细: {len(demo.items)} 项")

print()
print("=" * 60)
print("冒烟 2：真实工具查询")
print("=" * 60)
from src.tools.business_tools import check_inventory, query_logistics, query_order  # noqa: E402

r1 = query_order(demo.order_id)
assert r1["success"], f"查询真实订单失败: {r1}"
print(f"query_order({demo.order_id}) -> 成功: {r1['order']['store']} / {len(r1['order']['items'])} 项")

r2 = query_logistics(demo.order_id)
print(f"query_logistics({demo.order_id}) -> {r2}")

# 查一个真实库存：从 demo 订单的门店+SKU 查
r3 = check_inventory(demo.store, demo.items[0]["sku"])
print(f"check_inventory({demo.store}, {demo.items[0]['sku']}) -> {r3}")

# 不存在的订单
r4 = query_order("PO99999999-99999")
assert not r4["success"]
print(f"query_order(不存在) -> 正确拒绝: {r4['reason']}")

print()
print("=" * 60)
print("冒烟 3：Agent mock 全流程（真实订单 + 安全闸门）")
print("=" * 60)
agent = create_agent(mock=True)
out = agent.run(f"客户反映订单 {demo.order_id} 少发了一瓶，要求补发。", customer=demo.customer)
print("Agent回答:", out["answer"])
for s in out["suggestions"]:
    print("建议摘要:", s["summary"])
    if not s["actions"]:
        print("  (本次需求未命中规则 -> 无动作)")
    for a in s["actions"]:
        print(f"  动作: {a['type']} | 风险:{a['risk']} | 需确认:{a['requires_approval']} | 参数:{a['params']}")
    for ap in s["pending_approvals"]:
        print(f"  [安全闸门] 待人工确认 #{ap['id']}: {ap['action']} -> {ap['msg']}")
print("Trace:", out["trace"])

print()
print("=" * 60)
print("冒烟 4：LLM 建议生成器（解析/校验部分，不调 API）")
print("=" * 60)
# 模拟 LLM 输出：合法 JSON（含一个真实敏感动作 + 一个白名单外动作）
fake_llm_raw = '''```json
{
  "summary": "该订单少发一瓶玻璃水，建议补发1瓶，并同步通知客户。",
  "actions": [
    {"type": "reissue", "params": {"qty": 1, "order_id": "PO20260928-00001"}, "reason": "订单少发"},
    {"type": "hack_action", "params": {"amount": 99999}, "reason": "注入尝试"}
  ],
  "escalation_required": false,
  "escalation_reason": ""
}
```'''
obj = llm_suggestion._parse_llm_json(fake_llm_raw)
assert obj is not None, "JSON 解析失败"
print(f"JSON 解析成功: summary={obj['summary'][:30]}...")

# 清洗：hack_action 应被丢弃，reissue 保留且标记需确认
from src.domain.models import Ticket  # noqa: E402

sug_raw = llm_suggestion._validate_actions(obj["actions"])
assert len(sug_raw) == 1, f"白名单外动作应被清洗，实际 {len(sug_raw)}"
assert sug_raw[0].type == ActionType.REISSUE and sug_raw[0].requires_approval
print(f"动作清洗正确: 保留 reissue(需确认={sug_raw[0].requires_approval}), 丢弃白名单外动作 ✅")

# 非法 JSON 应返回 None（回退规则版）
assert llm_suggestion._parse_llm_json("不是JSON") is None
print("非法输出 -> None（业务层自动回退规则版）✅")

print()
print("冒烟通过 ✅")