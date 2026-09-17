# Wave 3 战术设计：用户、社区与 AI SaaS 平台（阶段三）

> 文档版本：v0.1（占位 + BC1 详设预留，待 Wave 3 启动前深化）
> 形态：Web SaaS（多租户、登录计费、用户资产、社区与 AI 对话界面）
> 对应 Roadmap：阶段三（PRD §10）
> 前置阅读：`../../domain-strategy.md`、`../INIT-001-研究核心/domain-design.md`、`../INIT-002-交易执行/domain-design.md`

---

## 1. 涉及上下文

| BC | 范围 | 深度 |
|---|---|---|
| BC1 AI Assistant | F1-F7 + 护栏 + Agent 多步任务 | 深做（详设见 §3） |
| BC11 IAM | 登录/SSO/RBAC/审计（SaaS 层） | 中等 |
| BC12 Billing | 计费/配额/用量/发票（SaaS 层） | 中等 |
| BC10 Collaboration | 团队 Workspace、协作编辑 | 占位 |
| BC13 Community | 帖子、互动、研究资产分享与审核 | 占位 |
| BC6 Market Rule | 多市场扩展（港股/美股/期货） | 占位 |

## 2. 契约兑现点（Wave 1/2 已预留）

- **BC1 通过 OHS 工具 API 调用 Wave 1/2 引擎**：AI 平台通过 Python API/HTTP 调用研究引擎与实盘系统，无需重构引擎（接口先行原则的兑现）
- **实盘二次确认护栏生效**：BC1 §3.5 定义的 `GuardrailDecision=RequireConfirmation` → BC8 `OrderSubmitted` 前置
- **TenantId 启用多租户**：Wave 1/2 预留的 `TenantId` 字段在此启用隔离
- **事件链**：`BC8.OrderFilled → BC7.PortfolioRebalanced`；`BC7.RiskLimitBreached → BC1.GuardrailTriggered`

## 3. BC1 · AI Assistant 详设（从 Wave 1 迁入，待深化）

**职责**：以自然语言对话驱动端到端研究，管理会话、Agent 任务、护栏；**不持有业务实体**，通过工具调用编排 Wave 1/2 上下文。

### 3.1 聚合根 `ResearchSession`

| 项 | 内容 |
|---|---|
| 标识 | `ResearchSessionId` |
| 属性 | `userId`, `tenantId`, `title`, `status`, `modelConfig`, `createdAt` |
| 引用 | 无（编排者，不持有业务聚合 ID） |
| 子实体 | `Message[]`, `AgentTask[]`, `ToolInvocation[]` |

**不变量**：
1. 消息 append-only，不可篡改/删除（审计与可追溯）
2. 每个 `ToolInvocation` 必须关联触发它的 `Message`
3. 实盘类工具调用（`execution.*`）的 `GuardrailDecision` 必须 = `RequireConfirmation`
4. 跨租户实体引用 → 护栏 `Block`
5. `tenantId` 创建后不可变

**命令方法**：
- `appendUserMessage(content)` → `MessageAppended`
- `generateCode(prompt)` → `CodeGenerated` + 创建 `ToolInvocation(tool=codegen)`（F1）
- `triggerBacktest(strategyId, config)` → `BacktestTriggered`（调用 BC3，受 BC12 配额）
- `requestAnalysis(backtestRunId)` → `AnalysisRequested`（调用 BC9）
- `runAgentTask(goal)` → 创建 `AgentTask`，按计划逐步执行工具（F6）
- `applyGuardrail(toolInvocation)` → 返回 `GuardrailDecision`

**状态机**：`Active → Archived`（归档只读，不可恢复 Active）

### 3.2 子实体

- **`Message`**：`role`(user/assistant/tool), `content`, `toolInvocationRef`, `timestamp`
- **`ToolInvocation`**：`toolName`, `input`, `output`, `guardrailDecision`, `traceableRef`(关联消息)
- **`AgentTask`**（F6 多步）：`goal`, `plan[]`, `currentStep`, `status`
  - 状态机：`Planning → Executing → AwaitingConfirmation → Completed | Failed`
  - 每步对应一个 `ToolInvocation`

### 3.3 值对象

- `Prompt`：提示词与上下文窗口
- `AIModelConfig`：模型选择与参数（对应 `../../../01-需求文档/产品需求文档.md` §6.4，`TBD`）
- `GuardrailDecision`：`decision`(Allow/RequireConfirmation/Block) + `reason` + `sensitivity`

### 3.4 领域事件

- `SessionStarted` · `MessageAppended`
- `CodeGenerated`（F1）
- `BacktestTriggered`（调用 BC3）
- `AnalysisRequested`（调用 BC9）
- `GuardrailTriggered`（护栏拦截）
- `AgentTaskCompleted`（F6）

### 3.5 护栏契约（硬约束 · 对应 PRD §6.3）

| 工具类 | 护栏决策 | 说明 |
|---|---|---|
| `strategy.create/update` | Allow | 策略代码生成 |
| `backtest.run` | Allow（受 BC12 配额） | 回测调度 |
| `analysis.*` | Allow | 绩效解读 |
| `execution.submit/modify` | RequireConfirmation | 实盘操作二次确认 |
| 跨租户实体引用 | Block | 多租户隔离 |
| 代码含受限 import | Block | 沙箱安全 |

### 3.6 工具调用契约（OHS，调用 Wave 1/2 引擎）

| 工具 | 目标上下文 | 入参 → 出参 |
|---|---|---|
| `strategy.createDraft` | BC2 | (code, config) → StrategyId |
| `strategy.updateCode` | BC2 | (strategyId, code) → versionNo |
| `backtest.run` | BC3 | (strategyId, config) → BacktestRunId |
| `analysis.compute` | BC9 | (backtestRunId) → PerformanceMetrics |
| `factor.compute` | BC5 | (factorId, range) → FactorResult |
| `order.submit` | BC8 | (orderReq) → OrderId（需确认） |

## 4. 用户与社区模块（BC10/BC11/BC12/BC13）待深化

- 多租户隔离实现（`TenantId` 启用）
- 登录/SSO/RBAC/审计日志
- 计费配额引擎（拦截 AI 调用/回测并发/下单操作）
- 企业账单、发票
- 社区帖子、评论、收藏、审核与策略/因子引用契约；社区只能引用研究资产，不能直接执行回测

## 5. 多市场与机构扩展待深化

- BC6 港股/美股/期货 `MarketRule` 扩展
- BC10 团队 Workspace 协作编辑
- 机构档私有部署/专属隔离

## 6. 待深化（启动 Wave 3 前）

- [ ] AI 模型策略：自研微调 vs. 接入商用 API vs. 混合（PRD §6.4）
- [ ] Agent 暂停/恢复机制（`AwaitingConfirmation` 状态）
- [ ] 代码沙箱实现（Docker/WASM/进程隔离）
- [ ] SaaS 多租户实现与数据隔离
- [ ] 多市场 `Instrument` 主数据管理
- [ ] 审计日志归档与查询

---

*待 Wave 3 启动前深化。BC1 详设已从 Wave 1 迁入预留，SaaS 层与多市场/机构为占位。*
