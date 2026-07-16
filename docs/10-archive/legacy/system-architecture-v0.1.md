# SVQuant 架构设计

> 文档版本：v0.1（Draft · 探讨中）
> 最后更新：2026-07-07
> 维护者：SVQuant 架构组
> 状态：本文档定义引擎分层与形态演进，是 `02-domain/` 领域模型的技术落点。
> 关联：`01-prd.md`（需求）、`02-domain/`（领域建模）

---

## 1. 架构总览

三大模块 + SaaS 平台层 + 数据层。形态随阶段演进（CLI/SDK → Web SaaS）。

```
                        SVQuant
           ┌────────────────┴────────────────┐
           │                                │
     Research Engine                Trading Engine      （阶段一/二 CLI，阶段三 Web）
           │                                │
           └──────────────┬─────────────────┘
                     Quant Core（引擎层）
           ┌────────────────┴────────────────┐
           │                                 │
      Historical Feed                   Live Feed          （数据层）

   ──────── 阶段三叠加（Web SaaS）────────
   SaaS 平台层（IAM / Billing / 多租户）  +  AI Assistant  +  Web UI
```

> **接口先行（API-first）**：QuantCore/ResearchEngine/TradingEngine 的所有能力以 Python API + CLI 暴露，并预留 HTTP 适配层。阶段三 AI 平台与 Web UI 通过这些接口调用引擎，无需重构。

---

## 2. QuantCore 引擎分层

```
Quant Core
├── Data Engine（统一数据访问）
├── Factor Engine（因子计算）          ── VectorEngine
├── Factor Library（内置因子库）
├── Strategy Engine（策略定义/版本）
├── Backtest Engine（回测）           ── VectorEngine(简单) + EventEngine(复杂)
├── Portfolio Engine（仓位与组合管理）  ── Wave 2
├── Risk Engine（风险控制）            ── Wave 2
├── Execution Engine（订单执行）      ── Simulated/Live（EventEngine 驱动）
├── Analyzer（绩效分析）
├── Report Engine（报告生成）
└── Market Rule（市场规则：T+1、涨跌停、交易时间等，多市场扩展点）
```

---

## 3. 双引擎设计 ⭐

两类计算本质不同，采用双引擎架构：向量化求快、事件驱动求精确。

> **向量化回测已落地为可插拔适配层**（Native + VectorBT 双后端，详见 `05-backtest-adapter.md`）：
> ResearchEngine 经 `IBacktestEngine` 契约按 config 切后端，因子代码与公共 API 零改动。
> 事件驱动 `BacktestEngine`（bar-loop）保留为未来 EventEngine 基座。

> **详细实现设计见 `04-engine-design.md`**（VectorEngine 基座 NumPy/Pandas、因子表达式引擎、EventEngine 事件模型与回测/实盘统一）。

### 3.1 VectorEngine（向量化引擎）

- **特点**：批处理矩阵运算（NumPy/Pandas），适合批量计算
- **用途**：
  - 因子计算（Factor Engine）
  - 因子分析（IC/IR/分层/换手）
  - 简单/快速策略回测（如因子选股组合）
- **阶段**：Wave 1 1a/1b 引入

### 3.2 EventEngine（事件驱动引擎）

- **特点**：按 bar/事件驱动，逐根推进，支持复杂时序逻辑
- **用途**：
  - 复杂策略回测（T+1/涨跌停/条件单/持仓管理）
  - 模拟盘（Wave 2，实时行情驱动）
  - 实盘交易（Wave 2，实时行情 + 券商）
- **阶段**：Wave 1 1c 引入（策略回测）→ Wave 2 拓展（模拟/实盘）

### 3.3 与 ExecutionEngine 的协作

```
EventEngine          驱动事件流（按时间推进 + 触发策略逻辑）
    │
    ▼
ExecutionEngine      处理订单撮合
    ├── SimulatedExecutionEngine   回测：模拟撮合（应用 BC6 MarketRule）
    └── LiveExecutionEngine        实盘：对接券商（Wave 2）
```

- EventEngine 负责"按时间推进 + 触发策略逻辑"，ExecutionEngine 负责"订单怎么成交"
- **Wave 2 实盘 = EventEngine + 实时行情 + `LiveExecutionEngine`**，替换回测的 `SimulatedExecutionEngine`，策略代码零改动

### 3.4 引擎与阶段的对应

| 阶段 | VectorEngine | EventEngine | ExecutionEngine |
|---|---|---|---|
| Wave 1 1a | 因子研究 + 简单回测 | — | Simulated（回测） |
| Wave 1 1b | 因子分析深化 | — | Simulated |
| Wave 1 1c | — | 复杂策略回测 | Simulated |
| Wave 2 | — | 模拟盘 + 实盘 | Simulated → Live |

---

## 4. 形态演进（三大阶段）

> 对齐 `01-prd.md` §10：先研究、后实盘、再 AI 结合。引擎能力不变，应用入口与 SaaS 层随阶段叠加。

| 阶段 | 形态 | 模块 | SaaS 层 | AI |
|---|---|---|---|---|
| 阶段一 ResearchEngine | CLI/SDK | QuantCore + ResearchEngine | 无 | 无 |
| 阶段二 TradingEngine | CLI/SDK | + TradingEngine | 无 | 无 |
| 阶段三 AI 平台 | Web SaaS | + AI Assistant + SaaS 层 | 多租户/计费/登录 | 有 |

**演进要点**：
- 阶段一/二引擎以 Python API + CLI 落地，研究员写因子库/策略 py 文件运行
- 阶段三在引擎之上叠加 Web SaaS 层（IAM/Billing/多租户）与 AI 对话界面，通过预留接口调用引擎
- `TenantId` 在阶段一/二预留字段（单租户默认值），阶段三启用多租户隔离

---

## 5. 多市场扩展

`Market Rule` 是多市场扩展的唯一改动点：

> 新增市场 = 新增一个 `MarketRule` 实例 + 对应 `Instrument` 数据源，**无需改动 Backtest/Execution 引擎逻辑**。

- Wave 1：A 股（`CN_A_SHARE`：T+1、10%/20% 涨跌停、100 股/手）
- Wave 3：港股/美股/期货扩展（对应 `Market` 值对象新增枚举）

---

## 6. 接口先行（API-first）

| 接口形式 | 阶段一/二 | 阶段三 |
|---|---|---|
| Python API | ✅ 实现（研究员直接调用） | ✅ AI 平台调用 |
| CLI | ✅ 实现（命令行运行） | ✅ 辅助 |
| HTTP 适配层 | ✅ 研究回测 API 已落地（`docs/06-research-api.md`，FastAPI） | ✅ AI 平台远程调用 |

> 研究回测的 HTTP 适配层已提前落地（`POST /api/backtest`：提交因子代码 -> 回测 -> 返回指标+净值），
> 详见 `docs/06-research-api.md`。其余 HTTP（实盘交易、AI 平台远程调用）仍按阶段三叠加。
> 阶段一/二引擎以 Python API + CLI 落地，阶段三在引擎之上叠加 Web SaaS 层（IAM/Billing/多租户）与 AI 对话界面，通过预留接口调用引擎。

---

## 7. 领域上下文 ↔ 引擎映射

| 领域上下文（BC） | 引擎/模块 | 阶段 |
|---|---|---|
| BC2 Strategy | Strategy Engine | Wave 1 |
| BC3 Backtest | Backtest Engine（VectorEngine + EventEngine） | Wave 1 |
| BC4 Data | Data Engine | Wave 1 |
| BC5 Factor | Factor Engine（VectorEngine）+ Factor Library | Wave 1 |
| BC6 Market Rule | Market Rule | Wave 1 |
| BC9 Analysis & Report | Analyzer + Report Engine | Wave 1 |
| BC10 Collaboration | — | Wave 1(社区) / Wave 3(团队) |
| BC7 Portfolio & Risk | Portfolio + Risk Engine | Wave 2 |
| BC8 Execution | Execution Engine（LiveExecutionEngine） | Wave 2 |
| BC1 AI Assistant | — | Wave 3 |
| BC11 IAM / BC12 Billing | SaaS 平台层 | Wave 3 |

> 详见 `02-domain/00-strategy.md` §8。

---

## 8. 待确认事项

- [x] **VectorEngine 实现基座**：NumPy + Pandas（详见 `04-engine-design.md` §2）。
- [x] **EventEngine 事件模型**：事件驱动框架，回测以 MarketEvent（bar）时间步进为主驱动，回测/实盘统一事件抽象（详见 `04-engine-design.md` §3）。
- [ ] **BC6 规则快照粒度**：`MarketRuleProfile` 是规则全集快照还是引用 + 版本号？影响回测可复现性。
- [ ] **BC4 Instrument 主数据**：自建 vs. 对接第三方（Tushare/聚源）？
- [ ] **HTTP 适配层接口契约**：阶段一/二预留的 HTTP 接口 schema 是否现在就定义？

---

*本文档为 v0.1 探讨稿。引擎详细设计随 Wave 1 实现推进深化。*
