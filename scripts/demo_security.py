# -*- coding: utf-8 -*-
"""安全加固演示：参数名规范化 + 库存闸门。

用法：python scripts/demo_security.py
不依赖 API key（纯安全层 + 数据源验证）。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.domain.models import Action, ActionType, RiskLevel  # noqa: E402
from src.safety.gate import SafetyGate  # noqa: E402
from src.agent import create_agent  # noqa: E402
from src.data_source import DataSource  # noqa: E402

print("=" * 66)
print("场景 1：LLM 参数别名攻击 —— quantity 不再绕过数量上限")
print("=" * 66)
gate = SafetyGate()
# LLM 用别名 quantity 输出一个超大补发数量（原本 qty 校验会失效）
attack = Action(ActionType.REISSUE, {"quantity": 9999, "order_id": "PO1"}, RiskLevel.HIGH)
ok, req, msg = gate.check(attack, "T1")
print(f"check(reissue, quantity=9999): 放行={ok} 说明={msg}")
# 规范化后 quantity->qty，qty=9999 > 上限 10 -> 应被拦
assert ok is False, "参数别名（quantity）应被规范化后拦截"
print("✅ 参数别名被规范化，超限补发被拦截")

print()
print("=" * 66)
print("场景 1b：count 别名同样生效")
print("=" * 66)
attack2 = Action(ActionType.REISSUE, {"count": 9999, "order_id": "PO1"}, RiskLevel.HIGH)
ok2, _, msg2 = gate.check(attack2, "T2")
assert ok2 is False
print(f"check(reissue, count=9999): 放行={ok2} 说明={msg2} -> 被拦截 ✅")

print()
print("=" * 66)
print("场景 1c：别名 money/price -> amount 统一退款金额校验")
print("=" * 66)
# money=99999 超上限，规范化后应被拦
attack3 = Action(ActionType.REFUND, {"money": 99999, "order_id": "PO1"}, RiskLevel.HIGH)
ok3, _, msg3 = gate.check(attack3, "T3")
print(f"check(refund, money=99999): 放行={ok3} 说明={msg3}")
assert ok3 is False
print("✅ 金额别名被规范化，超限退款被拦截")

# 缺失关键参数 -> 直接拒绝（之前 404 会误报"格式错误"）
attack4 = Action(ActionType.REFUND, {"note": "没有金额"}, RiskLevel.HIGH)
ok4, _, msg4 = gate.check(attack4, "T4")
print(f"check(refund, 缺金额): 放行={ok4} 说明={msg4}")
assert ok4 is False and "缺失" in msg4
print("✅ 关键参数缺失被明确拒绝")

print()
print("=" * 66)
print("场景 2：库存闸门 —— 补发前校验库存")
print("=" * 66)
ds = DataSource()
ds.load()
# 找一个可用库存很少的商品组合（缺货/不足）
order = ds.all_orders()[0]
store = order.store
sku = order.items[0]["sku"]
inv = ds.get_inventory(store, sku)
print(f"目标: 门店={store} sku={sku} 可用库存={inv['available'] if inv else '无'}")

# 用一个超大补发数量（> 库存）触发拦截
agent = create_agent(mock=True)
big = Action(ActionType.REISSUE, {"qty": 1000000, "order_id": order.order_id}, RiskLevel.HIGH)
ok_inv, inv_msg = agent._inventory_gate(big, order)
print(f"库存闸门(补发{1000000}): 通过={ok_inv} 说明={inv_msg}")
assert ok_inv is False
print("✅ 库存不足 -> 拦截补发")

# 正常数量应通过（若库存充足）
if inv and inv["available"] > 0:
    small = Action(ActionType.REISSUE, {"qty": 1, "order_id": order.order_id}, RiskLevel.HIGH)
    ok_inv2, inv_msg2 = agent._inventory_gate(small, order)
    print(f"库存闸门(补发1): 通过={ok_inv2} 说明={inv_msg2}")

print()
print("=" * 66)
print("完整链路：真实 LLM 输出别名参数也不绕过闸门（走 mock 全流程）")
print("=" * 66)
out = agent.run(f"客户反映订单 {order.order_id} 少发了一瓶，要求补发。", customer=order.customer)
for s in out["suggestions"]:
    print("摘要:", s["summary"])
    for a in s["actions"]:
        inv_note = a["params"].get("inventory_note", "")
        print(f"  action: {a['type']} | params={a['params']}" + ("  [库存:" + inv_note + "]" if inv_note else ""))

print()
print("安全加固验证完成 ✅")