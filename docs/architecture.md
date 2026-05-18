# 架构说明：AI-Ticket-Operations-Agent

> 本文档说明各层职责、数据流、设计取舍，是面试讲解与后续开发的依据。
> 与《项目立项方案-企业级智能工单售后Agent.md》配套。

## 架构分层

```
消费者 (报障/咨询)
   │ 自助入口 (轻量)
   ▼
┌──────────────────────────────────────────────┐
│ 编排层 src/agent.py                            │
│   LLM + Tool Calling 主循环 (max_rounds)       │
└───────┬───────────────┬───────────────┬──────┘
        │               │               │
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌────────────────┐
│ 工具层 tools  │ │ 安全层 safety │ │ 记忆层 memory  │
│ query_order  │ │ 白名单+闸门   │ │ 会话记忆+画像  │
│ query_...    │ │ 二次确认      │ │ (短期/长期)    │
└──────────────┘ └──────────────┘ └────────────────┘
        │               │
        ▼               ▼
┌──────────────────────────────────────────────┐
│ 可观测层 observability/trace.py（Trace+指标） │
│ 评测层 evaluation/runner.py（评测集+指标）    │
└──────────────────────────────────────────────┘
```

## 各层职责

### domain/ 领域模型
- `Ticket`（工单）、`Order`（订单）、`Action`（动作）、`Suggestion`（建议）、`AuditRecord`（留痕）
- `ActionType` + `ACTION_RISK`：**敏感动作硬编码风险等级**，是安全闸门的依据。

### models/ 模型接入
- 走 OpenAI 兼容接口（`chat_with_tools`），模型是插件：换模型只改 `.env`。
- 为多模型对比评测预留（evaluation）。

### tools/ 工具层
- **工具即业务边界**：新增业务 = 新增工具，不改编排层。
- `ToolRegistry` 统一注册，向外暴露 OpenAI 兼容的 function schema。
- MVP 工具：`query_order` / `query_logistics` / `check_inventory` / `create_suggestion` / `escalate_ticket`（后两者写建议/升级，见 business_tools）。

### safety/ 安全层（核心差异化）
- `SafetyGate.check()`：**动作类型白名单 → 参数校验 → 敏感动作转二次确认**。
- 规则：
  1. 敏感动作（退款/补发/改单/作废）= HIGH = **必须人工确认**；
  2. 只读/建议 = LOW = 自动放行；
  3. **失败默认拒绝**：任何异常 → 拒绝并升级人工；
  4. 安全**不依赖 LLM 自觉**，全部代码强制。
- `approve/deny`：人工二次确认的批准/驳回，落审计。

### memory/ 记忆层
- 短期 `SessionMemory`：同 session 跨轮上下文 + TTL + 滑动窗口 + 摘要（TODO）。
- 长期 `UserProfileMemory`：跨会话用户/门店画像，注入上下文降低重复沟通。
- MVP 内存实现，接口抽象（可换 Redis / 向量库）。

### observability/ 可观测
- `Tracer`：记录每次调用（tool/action/llm），含耗时、结果、审批人、decision。
- `summary()`：产出成功率、拒绝数、平均延迟，供评测与汇报。

### evaluation/ 评测层（杀手锏）
- 三类评测集：`normal` / `boundary` / `attack`。
- `EvalRunner`：跑用例 → 汇总通过率（分类别）→ 输出报告文本。
- 评测集预置在 `make_cases()`（W3 扩充）。

## 一次工单处理的完整数据流

1. 用户输入进入 `agent.run()` → 注入用户画像（长期记忆）+ 会话历史。
2. Agent（LLM）决定调用工具 → `_dispatch_tool()` 执行。
3. 工具返回结构化结果，回填给 LLM。
4. LLM 产出处理建议 `Suggestion`，内含 `Action`。
5. 每个 `Action` 过 `SafetyGate.check()`：
   - LOW 直接放行；
   - HIGH 生成 `ApprovalRequest`，暂停等待人工。
6. 人工 `approve/deny` → 落 `AuditRecord`。
7. 全程 `Tracer`记录 → `summary()` 指标。

## 设计取舍（面试可讲）

| 问题 | 取舍 | 理由 |
|---|---|---|
| 为什么敏感动作要人工确认？ | 代码闸门 + 人工 | 可追责、可回滚；LLM 不可作为资金/商品操作的唯一决策 |
| 为什么不用全局布尔标志？ | 进程内状态只用于会话 | 多用户并发会串扰；生产用 Redis 持久化 |
| 为什么评测内置？ | 每次调用落指标 | 评测不是事后动作，而是数据资产 |
| 为什么工具即边界？ | 新增业务=新增工具 | 不侵入编排层，可维护、可扩展 |

## 下一步（按里程碑）

- W1：完成工具层 + 工单接入 + Agent 基本流程（当前骨架已具备）。
- W2：安全闸门细化（库存闸门接入真数据、参数校验补全）。
- W3：记忆摘要压缩（LLM）、评测集扩充、指标面板。
- W4：审计面板 + 演示闭环 + 项目文档。
