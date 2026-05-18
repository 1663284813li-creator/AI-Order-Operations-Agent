# AI-Ticket-Operations-Agent

企业级智能工单 / 售后运营 Agent —— 给企业内部客服/运营团队用的工单处理助手。

## 一句话定位

消费者反馈的问题进入系统后，Agent 自动查单、审核、给出处理建议；敏感操作（退款/补发等）必须通过代码级安全闸门与人工二次确认；全程留痕可审计；异常自动升级人工兜底。

## 设计原则

1. **安全优先**：敏感动作永远由代码 + 人工共同控制，不依赖大模型自觉。
2. **人机协同**：明确"什么自动做、什么必须人审、异常如何兜底"。
3. **可评测**：评测不是事后动作，而是随每次工具调用落指标。
4. **多模型接入**：模型是插件不是绑定，支持多模型对比。

## 目录结构

```
AI-Ticket-Operations-Agent/
├── config/            # 配置（本地无密钥配置）
├── data/mock/         # 模拟数据（订单/物流/库存/工单）
├── docs/              # 架构与说明
├── logs/              # 运行时日志（gitignore）
├── scripts/           # 入口脚本（run.py）
├── src/
│   ├── domain/        # 领域模型：工单/订单/动作/建议
│   ├── models/        # 模型接入层（多模型 OpenAI 兼容）
│   ├── tools/         # 工具层：查单/物流/库存/建议/摘要
│   ├── safety/        # 安全层：白名单/闸门/二次确认
│   ├── memory/        # 记忆层：会话记忆 + 用户画像
│   ├── observability/ # 可观测：trace + 日志
│   ├── evaluation/    # 评测层：评测集/执行/指标
│   ├── agent.py       # 编排层（LLM + 工具调用主循环）
│   ├── config.py      # 全局配置
│   └── logger.py      # 日志
└── tests/             # 测试
```

## 快速开始

```bash
# 1. 建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 2. 装依赖
pip install -r requirements.txt

# 3. (可选) 配置模型密钥，启用真实 LLM 建议
copy .env.example .env   # 填入 MODEL_API_KEY / MODEL_BASE_URL / MODEL_NAME

# 4. 运行
.venv\Scripts\python.exe scripts\run.py        # mock 模式（无需 key）
.venv\Scripts\python.exe scripts\run.py --llm  # 真实 LLM 模式（需 .env）
```

## 数据源

查询类工具（查单/物流/库存）默认读取 `data/mock/` 下的**极客云模拟导出 CSV**（已内置，
无需额外下载）：
- `data/mock/orders.csv`  —— 订单明细（5000 行，一单多 SKU，含真实比例脏数据）
- `data/mock/inventory.csv` —— 门店库存（5000 行）
- `data/mock/returns.csv` —— 售后退货（5000 行）

数据源在加载时会自动**清洗脏数据**（空订单号/空商品/负数数量），并聚合多 SKU 明细、
按（门店,SKU）索引库存。可通过 `DataSource().dirty_stats()` 查看清洗统计。

## 两种运行模式

| 模式 | 触发 | 说明 |
|---|---|---|
| mock | 无 key / `--llm` 未传 | 规则生成建议 + 安全闸门，无需 API，可演示完整流程 |
| 真实 LLM | `--llm` 且已配 key | LLM 生成处理建议 + 工具调用，多模型可切换 |

## 里程碑（见 docs/architecture.md 与立项方案）

- W1: MVP 跑通（工具层 + 工单接入 + 基本流程）✅ 已就绪
- W2: 安全闸门（敏感动作 + 二次确认 + 参数校验）
- W3: 记忆 + 评测（画像 + 评测集 + 指标面板）
- W4: 收口（审计面板 + 演示闭环 + 文档）

