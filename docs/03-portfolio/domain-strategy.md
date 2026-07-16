# SVQuant 领域战略设计

> 文档版本：v0.1（Draft · 探讨中）
> 最后更新：2026-07-07
> 维护者：SVQuant 架构组
> 状态：本文档定义**全局**战略边界，是所有波次战术设计（`01-wave1` ~ `03-wave3`）的共同前提。

---

## 0. 文档说明

本文档是 `02-domain` 目录的**全局战略设计**，采用 DDD 方法：

```
product/产品需求文档.md  ──(业务能力)──►  portfolio/initiatives/  ──(限界上下文)──►  architecture/system_architecture.md
   需求        00-strategy (全局边界)              引擎分层
              01~03-wave  (分波战术)
```

- **战略设计全局化**：子域、限界上下文、上下文映射在此一次性定边界。
- **战术设计分波次**：聚合/实体/值对象/不变量/状态机落到各 wave 文档，只对即将开发的上下文深做。
- **实现路径**：先研究（Wave 1，CLI/SDK）→ 后实盘（Wave 2，CLI/SDK）→ 再 AI 结合（Wave 3，Web SaaS）。AI 与 SaaS 层在 Wave 3 引入，前两阶段无 AI、无 SaaS。
- **接口先行（API-first）**：Wave 1/2 引擎暴露 Python API + CLI + 预留 HTTP 适配层，Wave 3 AI 平台通过这些接口调用引擎。
- 标识符用英文，描述用中文；`TBD` 待确认，`⭐` 标记核心子域。

---

## 1. 子域划分

| 子域 | 类型 | 说明 | 对应 PRD 章节 |
|---|---|---|---|
| AI 研究助手 | 核心子域 ⭐ | 平台差异化，对话式研究编排（Wave 3 引入） | §6 |
| 策略研究 | 核心子域 ⭐ | 策略定义与回测，研究闭环主干 | §5.3 |
| 回测执行 | 核心子域 ⭐ | 策略在历史数据上的仿真与绩效产出 | §5.3 |
| 数据 | 支撑子域 | 行情/基本面/另类数据统一访问 | §5.1 |
| 因子 | 支撑子域 | 因子定义、计算、分析 | §5.2 |
| 市场规则 | 支撑子域 | T+1、涨跌停、交易时段，多市场扩展点 | §5.3(C2) |
| 组合与风控 | 支撑子域 | 组合构建、风控规则、风险指标 | §5.4 |
| 执行/交易 | 支撑子域 | 券商接入、订单、实盘持仓 | §5.5 |
| 绩效分析与报告 | 支撑子域 | 归因、报告生成 | §5.7 |
| 协作与分享 | 支撑子域 | 社区、团队空间 | §5.8 |
| 身份与访问（IAM） | 通用子域 | 用户、角色、租户、权限（Wave 3） | §5.9 |
| 计费与配额 | 通用子域 | 订阅、档位、配额、用量、账单（Wave 3） | §5.9 / §8 |

> 判据：核心子域 = 平台差异化与盈利来源（AI 编排 + 研究闭环），需自研并投入最强人力；支撑子域 = 必备但非差异化能力；通用子域 = 可采购或标准化实现（IAM/Billing 优先用成熟方案）。

---

## 2. 限界上下文总览

共 **12 个限界上下文**（BC）。下表给出职责、核心聚合根、实现波次与战术详设落点。

| # | 限界上下文 | 子域 | 核心聚合根 | 波次 | 战术详设 |
|---|---|---|---|---|---|
| BC1 | AI Assistant | 核心 ⭐ | `ResearchSession`, `AgentTask` | W3 | `03-wave3` |
| BC2 | Strategy Research | 核心 ⭐ | `Strategy` | W1 | `01-wave1` |
| BC3 | Backtest | 核心 ⭐ | `BacktestRun` | W1 | `01-wave1` |
| BC4 | Data | 支撑 | `Dataset`, `Instrument` | W1 | `01-wave1` |
| BC5 | Factor | 支撑 | `Factor` | W1 | `01-wave1` |
| BC6 | Market Rule | 支撑 | `MarketRule` | W1 | `01-wave1` |
| BC7 | Portfolio & Risk | 支撑 | `Portfolio`, `RiskRule` | W2 | `02-wave2` |
| BC8 | Execution / Trading | 支撑 | `Order`, `BrokerConnection` | W2 | `02-wave2` |
| BC9 | Analysis & Report | 支撑 | `PerformanceReport`, `Attribution` | W1 | `01-wave1` |
| BC10 | Collaboration | 支撑 | `SharedArtifact`, `Workspace` | W1(社区) / W3(团队) | `01-wave1` / `03-wave3` |
| BC11 | Identity & Access | 通用 | `User`, `Tenant`, `Role` | W3 | `03-wave3` |
| BC12 | Billing & Quota | 通用 | `Subscription`, `Quota` | W3 | `03-wave3` |

> 波次说明：Wave 1 为研究引擎（CLI/SDK，无 SaaS）——BC2/3/4/5/6/9 + BC10(社区)；Wave 2 为实盘（CLI/SDK）——BC7/8；Wave 3 为 AI 平台（Web SaaS）——BC1 + BC11/BC12(SaaS 层) + 多市场/机构扩展。AI 与 SaaS 层在 Wave 3 引入。

---

## 3. 上下文映射（Context Map）

```
                          ┌─────────────────────┐
                          │   BC1 AI Assistant   │  核心编排者（Wave 3 引入）
                          │ (会话/任务/护栏)      │  (Tool Use 调用各上下文能力)
                          └──────────┬──────────┘
                                     │ OHS + PL (开放主机服务 + 发布语言)
       ┌──────────┬──────────────────┼──────────────────┬──────────────┐
       ▼          ▼                  ▼                  ▼              ▼
  ┌─────────┐ ┌────────┐    ┌────────────┐      ┌────────────┐   ┌──────────────┐
  │BC2 Strat│ │BC5 Fctr│    │ BC3 Backtest│     │BC9 Analysis│   │BC10 Collab   │
  │ Research│ │        │    │             │    │ & Report   │   │              │
  └────┬────┘ └───┬────┘    └──────┬──────┘    └─────▲──────┘   └──────▲───────┘
       │ C-S      │ C-S            │ C-S             │ C-S              │ ACL
       │          ▼                │                 │                  │ (引用)
       │     ┌────────┐           │                 │                  │
       │     │ BC4 Data│◄──────────┘                 │                  │
       │     └────┬───┘  C-S                        │                  │
       │          │ C-S                             │                  │
       │     ┌────┴───────┐                         │                  │
       │     │ BC6 Market │◄────────────────────────┘                  │
       │     │   Rule     │                                            │
       │     └────┬───────┘                                            │
       │          │ C-S                                                │
       │     ┌────▼──────────┐    ┌──────────────────┐                 │
       │     │ BC8 Execution │───►│ BC7 Portfolio    │                 │
       │     │   /Trading    │    │   & Risk         │                 │
       │     └──────┬────────┘    └──────────────────┘                 │
       │            │ ACL                                              │
       │            ▼                                                  │
       │       [外部 Broker]                                           │
       │                                                              │
  通用子域（Wave 3 横切）                                                │
  ┌────────────────┐   ┌────────────────────┐   ┌──────────────┐      │
  │ BC11 Identity   │   │ BC12 Billing&Quota │   │ (BC 通知,可选)│      │
  │ (IAM)          │   │                    │   └──────────────┘      │
  └────────────────┘   └────────────────────┘                         │
   Shared Kernel         配额拦截 BC1/BC3/BC8 调用                      │
   (User/Tenant/Permission)                                             │
```

**关键关系**（C-S = Customer-Supplier，ACL = 防腐层，OHS = 开放主机服务）：

| 关系 | 模式 | 说明 |
|---|---|---|
| BC1 → BC2/5/3/9/10 | OHS + PL | AI 通过各上下文暴露的工具 API 编排，AI 为 Customer（Wave 3） |
| BC2 → BC5 | C-S | 策略引用因子作为输入 |
| BC2 → BC4 | C-S | 策略引用标的池（Instrument） |
| BC5 → BC4 | C-S | 因子计算依赖行情/基本面数据 |
| BC3 → BC2/4/5/6 | C-S | 回测消费策略+数据+因子，应用市场规则 |
| BC3 → BC9 | C-S | 回测结果产出给分析 |
| BC3 → BC8 | 契约预留 | 回测定义 `ExecutionEngine` 抽象，BC8 实现实盘（Wave 2 兑现） |
| BC9 → BC3/BC8 | C-S | 分析消费回测或实盘结果 |
| BC8 → BC6/BC7 | C-S | 下单前应用市场规则与风控 |
| BC8 → Broker | ACL | 对接外部券商系统，防腐 |
| BC7 → BC3/BC8 | C-S | 组合/风控消费持仓快照 |
| BC6 → BC3/BC8 | Shared Kernel 候选 | 市场规则被回测与执行共享，`TBD` 是否提升为共享内核 |
| BC10 → BC2/5/9 | ACL | 分享物引用其他上下文实体（只读快照） |
| BC11 → 全部 | Shared Kernel | User/Tenant/Permission 身份横穿所有上下文（Wave 3） |
| BC12 → BC1/3/8 | C-S | 配额拦截 AI 调用、回测并发、下单操作（Wave 3） |

> **接口先行**：Wave 1/2 各上下文以 Python API + CLI 暴露能力，并预留 HTTP 适配层。Wave 3 BC1 通过这些接口（OHS）编排，无需重构引擎。

---

## 4. 实现波次总览

> 对齐 `../02-product/产品需求文档.md` §10：**先研究、后实盘、再 AI 结合**。AI 与 SaaS 层在 Wave 3 引入，前两阶段为 CLI/SDK 引擎。

### Wave 1 — 研究引擎（阶段一，CLI/SDK）→ `initiatives/INIT-001-research-core/domain-design.md`

研究员完成策略开发、因子研究、回测、绩效分析的完整闭环（**无 AI、无实盘、无 SaaS**）。

| BC | 范围 | 深度 |
|---|---|---|
| BC2 Strategy Research | 策略定义 + 版本管理 | 深做 |
| BC3 Backtest | 事件驱动回测 + 市场规则约束 + `ExecutionEngine` 抽象预留 | 深做 |
| BC4 Data | A 股日线 + 基本面 | 中等 |
| BC5 Factor | 表达式引擎 + 内置因子库 + IC/IR/分层分析 | 中等 |
| BC6 Market Rule | A 股规则集 + 多市场抽象 | 中等 |
| BC9 Analysis & Report | 标准绩效 + 归因分析 | 中等 |
| BC10 Collaboration | 社区分享（最小版，CLI 可导入/导出） | 最小 |

> **无 SaaS**：无登录/计费/多租户。`TenantId` 预留字段，单租户默认值。

### Wave 2 — 实盘交易系统（阶段二，CLI/SDK）→ `initiatives/INIT-002-trading-execution/domain-design.md`

研究产出的策略部署到实盘，含风控与组合（**无 AI、无 SaaS**）。

| BC | 范围 |
|---|---|
| BC7 Portfolio & Risk | 组合构建 + 风控规则 + 风险指标 |
| BC8 Execution | 券商接入 + 订单 + 实盘持仓（兑现 BC3 `ExecutionEngine` 契约） |

> **无 SaaS**：交易员通过命令行/脚本操作。

### Wave 3 — AI 完整平台（阶段三，Web SaaS）→ `initiatives/INIT-003-ai-platform/domain-design.md`

AI 对话研究助手结合研究引擎与实盘系统，形成完整 SaaS 平台。

| BC | 范围 |
|---|---|
| BC1 AI Assistant | F1-F7 + 护栏 + Agent 多步任务 |
| BC11 IAM | 登录/SSO/RBAC/审计（SaaS 层） |
| BC12 Billing | 计费分层/配额/用量/发票（SaaS 层） |
| BC10 Collaboration | 团队 Workspace、协作编辑 |
| BC6 Market Rule | 多市场扩展（港股/美股/期货） |

> **Web SaaS**：多租户、登录计费、AI 对话界面。`TenantId` 启用多租户隔离。AI 平台通过 Wave 1/2 预留的接口调用引擎。

---

## 5. 关键场景事件流（端到端 · 跨波次）

### 5.1 研究闭环（Wave 1，CLI/SDK，无 AI）

```
[研究员] 编写策略 py 文件 → 命令行运行回测
  └─► BC2: StrategyCreated / StrategyCodeUpdated
  └─► BC3: BacktestStarted
        └─(应用 BC6 MarketRule + BC4 Data + BC5 Factor)─►
        BC3: BacktestCompleted → BacktestResultPersisted
  └─► BC9: ReportGenerated（标准指标 + 归因）
[研究员] 因子库 py 文件定义因子 → BC5: FactorComputed → FactorAnalysisCompleted
```

### 5.2 实盘闭环（Wave 2，CLI/SDK，无 AI）

```
BC2: StrategyDeployed ──► BC8: BrokerConnected
BC8: OrderSubmitted ──(BC7 Risk 前置校验)─► BC8: OrderFilled / OrderRejectedByRisk
BC8: OrderFilled ──► BC7: PortfolioRebalanced
BC7: RiskLimitBreached ──► 告警
```

### 5.3 AI 闭环（Wave 3，Web SaaS）

```
[用户] 对话 "回测双均线策略过去3年"
  └─► BC1: SessionStarted（BC11 鉴权 / BC12 配额校验）
  └─► BC1: CodeGenerated ──► BC2: StrategyCreated（调用 Wave1 引擎 API）
  └─► BC1: BacktestTriggered ──► BC3: BacktestCompleted
  └─► BC1: AnalysisRequested ──► BC9: ReportGenerated
[用户追问] "为什么回撤大？" ──► BC1: MessageAppended（AI 解读）
AI Agent 多步: BC1: AgentTask（规划→生成→回测→解读→报告）
  └─ 涉及实盘操作 → GuardrailTriggered（RequireConfirmation，二次人工确认）
```

---

## 6. 通用语言（Ubiquitous Language）

> 领域内统一术语，开发与产品共用。区别于 `../02-product/产品需求文档.md` §12.1 面向用户的术语表。

| 术语 | 英文 | 定义 |
|---|---|---|
| 研究会话 | ResearchSession | 一次 AI 对话研究的上下文（Wave 3） |
| 策略 | Strategy | 可回测/可执行的量化决策逻辑 |
| 因子 | Factor | 影响收益的量化特征表达式 |
| 回测运行 | BacktestRun | 策略在历史数据上的一次仿真 |
| 标的 | Instrument | 可交易证券（股票/期货等），跨市场 |
| 市场规则 | MarketRule | 某市场的交易约束集合 |
| 组合 | Portfolio | 多策略/多标的的持仓组合 |
| 风控规则 | RiskRule | 下单前的约束（止损/仓位/禁投） |
| 持仓快照 | PositionSnapshot | 某时刻持仓状态 |
| 执行引擎抽象 | ExecutionEngine | 回测模拟撮合与实盘撮合的统一接口（Wave 1 定义，Wave 2 兑现） |
| 分享物 | SharedArtifact | 可社区分享的策略/因子/报告 |
| 租户 | Tenant | SaaS 多租户隔离单元（Wave 3 启用） |
| 档位 | SubscriptionTier | 计费分层标识（Wave 3） |
| 配额 | Quota | 档位对应的资源上限（Wave 3） |
| 护栏 | Guardrail | AI 行为的硬性约束决策（Wave 3） |

---

## 7. SaaS 多租户领域考量（Wave 3）

| 维度 | 设计 |
|---|---|
| 租户隔离 | `TenantId` 作为聚合根的隔离键，所有业务聚合（Strategy/Factor/Backtest 等）必带 `TenantId`。Wave 1/2 预留字段、单租户默认值，Wave 3 启用多租户无需改模型 |
| 共享 vs 专属 | 个人档共享池（逻辑隔离）；机构档专属 Schema/算力（物理隔离），同一领域模型，部署形态不同 |
| 数据隔离边界 | BC4 Data 的公开数据集可跨租户共享；BC2/3/5 等私有数据严格按 `TenantId` 隔离 |
| AI 跨租户隔离 | BC1 的对话上下文不得引用其他租户实体；护栏强制 `TenantId` 一致性校验（Wave 3） |
| 配额拦截点 | BC12 在 BC1(AI 调用)/BC3(回测并发)/BC8(下单) 前置拦截（Wave 3；Wave 1/2 无配额） |

---

## 8. 领域上下文 ↔ 架构模块映射

| 领域上下文 | ResearchEngine | TradingEngine | QuantCore | SaaS 平台层 |
|---|---|---|---|---|
| BC1 AI Assistant | ✓ | | | |
| BC2 Strategy Research | ✓ | | | |
| BC3 Backtest | | | Strategy Engine | |
| BC4 Data | | | Data Engine | |
| BC5 Factor | | | Factor Engine + Library | |
| BC6 Market Rule | | | Market Rule | |
| BC7 Portfolio & Risk | | | Portfolio + Risk Engine | |
| BC8 Execution | | ✓ + Execution Engine | | |
| BC9 Analysis & Report | | | Analyzer + Report Engine | |
| BC10 Collaboration | ✓ | | | |
| BC11 IAM | | | | ✓ |
| BC12 Billing | | | | ✓ |

> 说明：BC8 跨 TradingEngine（对外交易能力）与 QuantCore.Execution Engine（底层执行引擎），属同一限界上下文的两层实现。Wave 1/2 引擎以 CLI/SDK 形态落地，Wave 3 在其上叠加 Web SaaS 层。

---

## 9. 全局待确认事项

- [ ] **BC6 Market Rule 定位**：作为独立 BC（C-S）还是提升为 Shared Kernel？独立 BC 更内聚，Shared Kernel 性能更高但耦合更强。
- [ ] **BC1 AI Assistant 是否持有"研究产物"**：当前设计 AI 不持有策略/报告实体（只编排）。若需"AI 生成的报告"归 AI 所有，则 BC1 与 BC9 边界需重划。
- [ ] **BC4 Instrument 是否独立**：Instrument（标的）被多上下文引用，是否提升为共享内核或独立主数据上下文？
- [ ] **通知上下文**：是否新增 BC13 Notification（邮件/站内信/Webhook），用于风控告警、配额预警？
- [ ] **事件驱动实现**：领域事件采用进程内事件总线 vs. 消息队列（Kafka/RabbitMQ）？影响 BC1 的 Agent 编排与 BC3→BC9 的异步链路。
- [ ] **AI 模型策略对领域的影响**：`../02-product/产品需求文档.md` §6.4 若选自研微调，BC1 需新增 `ModelTraining` 子域；若纯接入商用 API，则 BC1 无需该子域。（Wave 3 启动前确认）
- [ ] **模拟盘归属**：阶段一末尾还是阶段二开头（当前归 Wave 2，对齐 PRD §10 2a）。
- [x] **HTTP 适配层时机**：Wave 1/2 仅预留接口，Wave 3 实现（已确认）。

---

*本文档为 v0.1 探讨稿。确认后将作为各波次战术设计文档的基线。战术细节见 `01-wave1` ~ `03-wave3`。*
