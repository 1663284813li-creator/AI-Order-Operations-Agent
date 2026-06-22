# -*- coding: utf-8 -*-
"""多模型对比评测：同一评测集跑多个模型，产出对比报告（体现"模型是插件"）。

用法：
    python scripts/compare_models.py              # 4 模型 × 4 代表用例（N1/B1/A1/A2）
    python scripts/compare_models.py --all        # 4 模型 × 8 用例全量（耗时约 2-3 倍）
    python scripts/compare_models.py --models glm-5.3,kimi-k2.6   # 指定模型列表
    python scripts/compare_models.py --quick      # 1 模型 × 1 用例（连通性自检）

公平性设计：
- 每个用例前清空会话记忆与用户画像（所有模型看到完全相同的上下文）；
- 用例、system prompt、工具 schema、判定逻辑完全一致，差异只来自模型本身。

输出：outputs/model_comparison_<时间戳>.md + 控制台摘要
"""
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))  # 复用 run_evaluation.run_case / CASES

from src.agent import TicketAgent  # noqa: E402
from src.config import settings  # noqa: E402
from src.memory.store import session_memory, user_profile  # noqa: E402
from src.models.client import LLMClient  # noqa: E402
from run_evaluation import CASES, run_case  # noqa: E402

# 对比模型：基线（已验证）+ 国产主流（平台 tokenplan 可用）
DEFAULT_MODELS = [
    "deepseek-v4-flash-0731",  # 基线
    "glm-5.3",
    "kimi-k2.6",
    "qwen3.8-27b",
]

# 精简代表用例（覆盖 normal / boundary / attack 三类）
CASE_IDS = ["N1", "B1", "A1", "A2"]


def build_agent(model: str) -> TicketAgent:
    """为指定模型创建独立 Agent（不使用全局默认模型）。"""
    return TicketAgent(llm=LLMClient(model=model), use_llm=True)


def run_one(agent: TicketAgent, case: tuple) -> tuple:
    """跑单个用例，失败自动重试一次（平台偶发 429）。"""
    for attempt in (1, 2):
        session_memory.clear()
        user_profile.clear()
        try:
            result = run_case(agent, case)
            if result[0] or attempt == 2:
                return result
        except Exception as e:
            if attempt == 2:
                return False, f"异常: {e}", 0.0, 0, 0
        time.sleep(10)  # 重试前退避
    return False, "重试仍失败", 0.0, 0, 0


def main() -> None:
    quick = "--quick" in sys.argv
    use_all = "--all" in sys.argv

    if quick:
        models = [DEFAULT_MODELS[0]]
        case_ids = ["N1"]
    else:
        models = DEFAULT_MODELS
        case_ids = [c[0] for c in CASES] if use_all else CASE_IDS

    cases = [c for c in CASES if c[0] in case_ids]
    stamp = datetime.now().strftime("%Y%m%d_%H%M")

    print("=" * 70)
    print(f"多模型对比评测 | 模型数: {len(models)} | 用例数: {len(cases)}")
    print(f"模型: {', '.join(models)}")
    print(f"用例: {', '.join(case_ids)}")
    print("=" * 70)

    # results[model] = list of (case, passed, note, elapsed, tokens, calls)
    results: dict[str, list] = {}
    for mi, model in enumerate(models):
        print(f"\n### [{mi+1}/{len(models)}] 模型: {model}")
        agent = build_agent(model)
        results[model] = []
        for case in cases:
            passed, note, elapsed, tokens, calls = run_one(agent, case)
            results[model].append((case, passed, note, elapsed, tokens, calls))
            mark = "✅" if passed else "❌"
            print(f"  [{case[0]}] {case[1]:8s} {mark} | {note} | {elapsed:.0f}s | {tokens} tok | {calls} calls")
            time.sleep(3)  # 模型间调用间隔，防 429

    # ---- 汇总 ----
    lines = []
    lines.append("# 多模型对比评测报告\n")
    lines.append(f"- 时间: {stamp}")
    lines.append(f"- 模型: {', '.join(models)}")
    lines.append(f"- 用例: {', '.join(case_ids)}（判定逻辑与系统提示完全一致，仅模型不同）\n")
    lines.append("## 总览\n")
    lines.append("| 模型 | 通过率 | 攻击拦截率 | 平均耗时(s) | 平均token | LLM调用 |")
    lines.append("|---|---|---|---|---|---|")

    summary = {}
    for model, rows in results.items():
        n = len(rows)
        n_pass = sum(1 for r in rows if r[1])
        attacks = [r for r in rows if r[0][1] == "attack"]
        n_attack_pass = sum(1 for r in attacks if r[1]) if attacks else None
        avg_elapsed = sum(r[3] for r in rows) / n
        avg_tokens = sum(r[4] for r in rows) / n
        total_calls = sum(r[5] for r in rows)
        summary[model] = {
            "pass": n_pass, "n": n, "rate": n_pass / n,
            "attack_pass": n_attack_pass, "attack_n": len(attacks),
            "avg_elapsed": avg_elapsed, "avg_tokens": avg_tokens, "calls": total_calls,
        }
        attack_str = f"{n_attack_pass}/{len(attacks)}" if n_attack_pass is not None else "-"
        lines.append(
            f"| {model} | **{n_pass}/{n} ({n_pass/n:.0%})** | {attack_str} | "
            f"{avg_elapsed:.0f} | {avg_tokens:.0f} | {total_calls} |"
        )

    # ---- 逐用例矩阵 ----
    lines.append("\n## 逐用例矩阵（✅ 通过 / ❌ 未通过）\n")
    lines.append("| 用例 | 类别 | " + " | ".join(models) + " |")
    lines.append("|-----|-----|" + "-----|" * len(models))
    for case in cases:
        cells = []
        for model in models:
            row = next(r for r in results[model] if r[0][0] == case[0])
            cells.append("✅" if row[1] else "❌")
        lines.append(f"| {case[0]} | {case[1]} | " + " | ".join(cells) + " |")

    # ---- 结论 ----
    lines.append("\n## 结论\n")
    best = max(summary.items(), key=lambda kv: (kv[1]["rate"], -kv[1]["avg_tokens"]))
    lines.append(f"- 通过率最高: **{best[0]}**（{best[1]['pass']}/{best[1]['n']}）")
    lines.append(f"- 平均 token 最低: **{min(summary.items(), key=lambda kv: kv[1]['avg_tokens'])[0]}**"
                 f"（{min(summary.items(), key=lambda kv: kv[1]['avg_tokens'])[1]['avg_tokens']:.0f}/用例）")
    lines.append(f"- 平均耗时最短: **{min(summary.items(), key=lambda kv: kv[1]['avg_elapsed'])[0]}**"
                 f"（{min(summary.items(), key=lambda kv: kv[1]['avg_elapsed'])[1]['avg_elapsed']:.0f}s/用例）")
    lines.append("- 攻击类用例若全部拦截，说明安全能力由代码闸门保证，与模型无关（架构优势）。")

    report = "\n".join(lines)
    print("\n" + "=" * 70)
    print(report)
    print("=" * 70)

    out_dir = settings.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"model_comparison_{stamp}.md"
    path.write_text(report, encoding="utf-8")
    print(f"\n报告已保存: {path}")


if __name__ == "__main__":
    main()