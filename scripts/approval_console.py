# -*- coding: utf-8 -*-
"""人工确认控制台（CLI）：查看待确认动作 -> 批准/驳回 -> 审计导出。

这是"人机协同闭环"的演示入口：
    Agent 建议 + 安全闸门生成"待人工确认" -> 运营人员在此批准/驳回 -> 全程留痕。

用法：
    python scripts/approval_console.py            # 交互式控制台
    python scripts/approval_console.py --demo     # 自动演示一轮（非交互）

控制台命令：
    list                查看待确认列表
    approve <id> <操作人>      批准（如: approve 140726947806560 李运营）
    deny <id> <操作人> <理由>  驳回
    audit               查看审计留痕
    export [path]       导出审计 JSON（默认 outputs/audit.json）
    new                 模拟一条新工单（生成待确认）
    quit                退出
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import settings  # noqa: E402
from src.safety.gate import safety_gate  # noqa: E402

DEFAULT_TICKET = "客户反映订单 PO20260928-00001 少发了一瓶玻璃水，要求补发。"


def print_pending() -> None:
    pend = safety_gate.pending_dicts()
    if not pend:
        print("  （当前无待确认动作）")
        return
    print(f"  {'ID':<20} {'动作':<14} {'风险':<8} 参数")
    print("  " + "-" * 70)
    for p in pend:
        params = json.dumps(p["params"], ensure_ascii=False)
        print(f"  {p['id']:<20} {p['action']:<14} {p['risk']:<8} {params}")
        print(f"    工单: {p['ticket_id']} | 原因: {p['reason'][:50]}")


def print_audit() -> None:
    rows = safety_gate.audit_dicts()
    if not rows:
        print("  （审计留痕为空）")
        return
    print(f"  {'时间':<20} {'工单':<24} {'动作':<14} {'操作人':<10} {'决定':<10} 备注")
    print("  " + "-" * 90)
    for r in rows:
        print(f"  {r['timestamp']:<20} {r['ticket_id']:<24} {r['action']:<14} "
              f"{r['operator']:<10} {r['decision']:<10} {r['note'][:30]}")


def export_audit(path: Path) -> None:
    rows = safety_gate.audit_dicts()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ 审计已导出: {path}（{len(rows)} 条记录）")


def simulate_new_ticket() -> None:
    """模拟一条工单：Agent 生成建议 -> 敏感动作进入待确认队列。"""
    from src.agent import create_agent

    agent = create_agent(mock=True)
    result = agent.run(DEFAULT_TICKET, customer="张三")
    for ap in result.get("pending_approvals", []):
        print(f"  → 新待确认 #{ap['id']}: {ap['action']} {ap['params']}")


def main() -> None:
    print("=" * 66)
    print("人工确认控制台 | SafetyGate 二次确认 + 审计留痕")
    print(f"模型: {settings.model_name} | 时间: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 66)

    if "--demo" in sys.argv:
        print("\n[自动演示] 模拟工单 -> 批准 -> 审计导出")
        simulate_new_ticket()
        print("\n--- 待确认列表 ---")
        print_pending()
        pend = safety_gate.pending_dicts()
        if pend:
            print(f"\n[自动演示] 操作人「李运营」批准 #{pend[0]['id']}")
            ok, msg = safety_gate.approve(str(pend[0]["id"]), "李运营")
            print(f"  → {msg}")
            print("\n--- 审计留痕 ---")
            print_audit()
            export_audit(settings.output_dir / "audit_demo.json")
        print("\n[自动演示] 完成。退出前先拒绝第二条? (y)")
        if input().strip().lower() == "y":
            pend = safety_gate.pending_dicts()
            if pend:
                safety_gate.deny(str(pend[0]["id"]), "李运营", "与仓库确认无少发，驳回")
                print_audit()
        return

    print("\n命令: list | approve <id> <操作人> | deny <id> <操作人> <理由> | "
          "audit | export [path] | new | quit")
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出")
            break
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()
        if cmd in ("quit", "exit", "q"):
            break
        elif cmd == "list" or cmd == "l":
            print_pending()
        elif cmd == "audit" or cmd == "a":
            print_audit()
        elif cmd == "new" or cmd == "n":
            simulate_new_ticket()
        elif cmd == "export":
            p = parts[1] if len(parts) > 1 else str(settings.output_dir / "audit.json")
            export_audit(Path(p))
        elif cmd == "approve" and len(parts) >= 3:
            ok, msg = safety_gate.approve(parts[1], parts[2])
            print(f"  → {msg}")
        elif cmd == "deny" and len(parts) >= 4:
            ok, msg = safety_gate.deny(parts[1], parts[2], " ".join(parts[3:]))
            print(f"  → {msg}")
        else:
            print("  用法: list | approve <id> <操作人> | deny <id> <操作人> <理由> | audit | export [path] | new | quit")


if __name__ == "__main__":
    main()