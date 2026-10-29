# Wave 1 战术设计：研究引擎（阶段一）

> 2026-08-28 架构修订：用户已确认 ADR-029 的常规 FastAPI 分层。
> 原 QuantCore 运行时边界取消；五个 Engine 的业务逻辑进入 `app.services`，
> Panel、MetricContext、回测规格/结果和实验上下文进入 `app.models`，数据访问进入 `app.database`。
> 配置为 `app.config`，通用工具为 `app.utils`；不增加 domain/application/infrastructure。
> 下文中的旧目录和旧分层仅作历史设计追溯，不再作为新代码约束；既有业务规则和历史验证记录保留。
> 详见根目录 FEAT-030/README.md 与 ADR-029。FEAT-029 因子来源加载目标保持不变。


> 文档版本：v0.1（Draft · 探讨中）
> 最后更新：2026-07-07
> 形态：CLI/SDK（无 Web 界面、无 SaaS 层）
> 对应 Roadmap：阶段一（PRD §10）
> 前置阅读：`../../../架构与技术/领域战略.md`
> 状态：本波次为**当前实现焦点**，覆盖 QuantCore + ResearchEngine 的策略与因子研究最小闭环（**无 AI、无 SaaS**）。

---

## 0. 范围与设计约定

### 0.1 本波次覆盖

| BC | 上下文 | 深度 | PRD 对应 |
|---|---|---|---|
| BC2 | Strategy Research | 深做 | C1, C3 |
| BC3 | Backtest | 深做 | C2, C3 |
| BC4 | Data | 中等 | A1, A2 |
| BC5 | Factor | 中等 | B1, B2, B3 |
| BC6 | Market Rule | 中等（含多市场抽象） | C2(Market Rule) |
| BC9 | Analysis & Report | 中等（含归因） | G1, G2 |
| BC10 | Collaboration | 最小（CLI 导入导出） | H1 |

> **不含**：BC1 AI（Wave 3）、BC7/BC8 实盘（Wave 2）、BC11/BC12 SaaS 层（Wave 3）。

### 0.2 战术设计约定

- **形态**：CLI/SDK。研究员在因子库/策略 py 文件中写代码，命令行运行；引擎暴露 Python API。
- **接口先行（API-first）**：所有引擎能力暴露 Python API + CLI；HTTP 适配层 Wave 1/2 仅预留接口、Wave 3 实现，供 AI 平台调用。
- **聚合根**：一致性边界，外部只持有其 ID 引用，不持有对象。
- **不变量**：聚合必须始终满足的规则，写明以便实现时校验。
- **命令方法**：聚合根上的状态变更入口，触发领域事件。
- **状态机**：用 `A → B` 表示合法迁移。
- **隔离键**：所有业务聚合根带 `TenantId`（**Wave 1 预留字段，单租户默认值；Wave 3 启用多租户**）。
- **契约预留**：为 Wave 2（实盘）/ Wave 3（AI）预留接口，标注 `▶预留`。

---

## 1. BC2 · Strategy Research（策略研究）⭐

**职责**：策略定义、版本管理；与回测解耦（策略是"定义"，回测是"执行"）。

### 1.1 聚合根 `Strategy`

| 项 | 内容 |
|---|---|
| 标识 | `StrategyId` |
| 属性 | `tenantId`, `ownerId`, `name`, `currentVersionNo`, `status` |
| 引用 | `factorIds[]`(BC5), `instrumentPoolIds[]`(BC4) —— 仅 ID |
| 子实体 | `StrategyVersion[]` |

**不变量**：
1. 版本号单调递增，不可回退（可新建版本回滚）。
2. `Deployed` 状态的策略不可删除其代码版本。
3. 发布到社区需 owner 权限。
4. `tenantId` 不可变。

**命令方法**：
- `createDraft(code, config)` → `StrategyCreated`（v1）
- `updateCode(code, changeNote)` → `StrategyCodeUpdated`（新版本）
- `publish()` → `StrategyPublished`（触发 BC10，导出/分享）
- `deploy(target)` → `StrategyDeployed`（target = simulate/backtest/live；live 在 Wave 2 兑现）
- `getExecutableCode()` → 返回当前版本代码（供 BC3 回测）

**状态机**：`Draft → Published → Deployed`（可回退到 Published，不可回退到 Draft）

### 1.2 子实体与值对象

**`StrategyVersion`**：`versionNo`, `code`(StrategyCode), `createdAt`, `changeNote`
**`StrategyCode`**：Python 代码体 + 依赖声明
**`StrategyConfig`**：参数默认值、标的池引用、默认回测区间

### 1.3 领域事件

- `StrategyCreated` · `StrategyCodeUpdated` · `StrategyPublished` · `StrategyDeployed`

---

## 2. BC3 · Backtest（回测执行）⭐

**职责**：在历史数据上仿真策略，产出交易记录、持仓快照与原始绩效。一个策略可多次回测。

**引擎（双引擎架构）**：
- **VectorEngine（向量化）**：简单/快速回测（如因子选股组合），批处理矩阵运算（NumPy/Pandas），Wave 1 1a 引入。
- **EventEngine（事件驱动）**：复杂策略回测（T+1/涨跌停/条件单），按 bar 驱动，Wave 1 1c 引入；Wave 2 拓展模拟盘/实盘。

### 2.1 聚合根 `BacktestRun`

| 项 | 内容 |
|---|---|
| 标识 | `BacktestRunId` |
| 属性 | `tenantId`, `status`, `startedAt`, `completedAt` |
| 引用 | `strategyId`, `strategyVersionNo`, `marketRuleProfile`(BC6), `datasetRef`(BC4) |
| 配置 | `BacktestConfig`：period, frequency, initialCapital, commission |
| 子实体 | `TradeRecord[]`, `PositionSnapshot[]` |
| 结果 | `BacktestResult`：收益序列、回撤等原始数据 |

**不变量**：
1. 必须引用有效 `strategyId` + `strategyVersionNo`。
2. `Running` 状态不可修改配置。
3. 持仓受 MarketRule 约束（T+1、涨跌停）—— 由 BC6 注入。
4. 不可超买（现金约束）—— **内置市场规则约束，非 BC7 业务风控**（见 §2.4 边界）。
5. `tenantId` 不可变。

**命令方法**：
- `start()` → `BacktestStarted`
- `applyMarketRule(marketRule)` → 逐 bar 应用 T+1/涨跌停/交易时段
- `recordTrade(trade)` → 追加 `TradeRecord`
- `snapshotPosition(date, positions)` → 追加 `PositionSnapshot`
- `complete(result)` → `BacktestCompleted` + `BacktestResultPersisted`（触发 BC9）
- `fail(reason)` → `BacktestFailed`

**状态机**：`Pending → Running → Completed | Failed`

### 2.2 子实体与值对象

**`TradeRecord`**：`timestamp`, `instrumentId`, `side`, `qty`, `price`, `commission`
**`PositionSnapshot`**：`date`, `positions[]`(instrumentId, qty, mktValue)
**`BacktestConfig`**：见上
**`MarketRuleProfile`**：引用 BC6 的规则集快照（回测期间不可变）
**`BacktestResult`**：equityCurve, drawdownSeries, tradeCount

### 2.3 领域事件

- `BacktestStarted` · `BacktestCompleted` · `BacktestFailed` · `BacktestResultPersisted`

### 2.4 内置风控 vs BC7 实盘风控的边界 ⚠️

| 维度 | BC3 回测内置 | BC7 实盘风控（Wave 2） |
|---|---|---|
| 性质 | 市场规则约束 | 业务风控规则 |
| 内容 | T+1、涨跌停、现金不超买、交易时段 | 止损、仓位上限、禁投池 |
| 来源 | BC6 MarketRule 注入 | `RiskRule` 配置 |
| 可选性 | 回测必须遵守 | 回测可作可选前置，实盘必须 |

> Wave 2 时 BC7 可作为回测的可选风控前置注入，不破坏 BC3 内置不变量。

### 2.5 执行引擎抽象（▶预留 BC8）⭐ 关键契约

为 Wave 2 实盘预留，使策略代码与撮合逻辑解耦：

```
interface ExecutionEngine {        // 端口：订单撮合
  submit(order) -> fill
}

class SimulatedExecutionEngine     // BC3 用：回测内模拟撮合（应用 BC6）
class LiveExecutionEngine          // BC8 用：对接券商（Wave 2 实现）
```

**EventEngine 与 ExecutionEngine 协作**：EventEngine 驱动事件流（按时间推进 + 触发策略逻辑），ExecutionEngine 处理订单撮合（Simulated 回测 / Live 实盘）。Wave 2 实盘 = EventEngine + 实时行情 + `LiveExecutionEngine`。

**收益**：Wave 2 做实盘时，BC8 实现 `LiveExecutionEngine` 替换模拟实现，BC3 回测逻辑零改动。

---

## 3. BC4 · Data（数据访问）

**职责**：行情/基本面/另类数据统一访问。数据量大，记录不作为聚合内实体，通过查询服务读。

### 3.1 聚合根

**`Instrument`**（标的，跨市场主数据）
- 标识：`InstrumentId`（或 `Symbol + Market`）
- 属性：`symbol`, `market`, `type`(股票/指数/期货), `name`
- 不变量：`Symbol+Market` 唯一

**`Dataset`**（数据集元数据）
- 标识：`DatasetId`
- 属性：`tenantId`, `name`, `type`(行情/基本面/另类), `source`, `scope`
- 命令：`register()` → `DatasetRegistered`，`refresh()` → `DataUpdated`

### 3.2 值对象（按需查询，非聚合内实体）

- `Bar`：`date`, `OHLCV`, `adjustment`(复权)
- `FundamentalRecord`：`instrumentId`, `reportDate`, `fields[]`
- `Symbol`, `Market`, `Timeframe`, `Adjustment`

### 3.3 领域事件

- `DataUpdated` · `DatasetRegistered`

### 3.4 Wave 1 范围

- A 股日线行情 + 基本面财务数据（PRD A1, A2）
- 分钟/Tick/另类/港美股留后续波次

---

## 4. BC5 · Factor（因子研究）

**职责**：因子定义、表达式求值、因子值计算与有效性分析。因子作为策略输入。

**引擎**：**VectorEngine（向量化）**，批处理矩阵运算（NumPy/Pandas），Wave 1 1a/1b 引入。因子计算与 IC/IR/分层分析本质是批量矩阵运算，向量化最合适。

### 4.1 聚合根 `Factor`

| 项 | 内容 |
|---|---|
| 标识 | `FactorId` |
| 属性 | `tenantId`, `ownerId`, `name`, `currentVersionNo`, `status` |
| 子实体 | `FactorVersion[]` |
| 值对象 | `FactorExpression`, `FactorMetrics` |

**不变量**：
1. 表达式语法必须合法（由表达式引擎校验）。
2. 版本号单调递增。
3. `tenantId` 不可变。

**命令方法**：
- `define(expression, name)` → `FactorDefined`（v1）
- `updateExpression(expr, note)` → `FactorUpdated`（新版本）
- `compute(range)` → `FactorComputed`（计算因子值，依赖 BC4 数据）
- `analyze()` → `FactorAnalysisCompleted`（IC/IR/分层/换手）
- `getFactorResult(range)` → 返回因子值（供 BC3 回测引用）

**状态机**：`Draft → Published → Deprecated`

### 4.2 子实体与值对象

**`FactorVersion`**：`versionNo`, `expression`, `createdAt`, `changeNote`
**`FactorExpression`**：表达式语法树，类 WorldQuant Alpha 101 风格（已确认；具体语法细则待实现时定）
**`FactorMetrics`**：`IC`, `IR`, `分层收益`, `换手率`, `相关性`
**`FactorResult`**：`instrumentId`, `date`, `value`（计算结果，可缓存）

### 4.3 领域事件

- `FactorDefined` · `FactorUpdated` · `FactorComputed` · `FactorAnalysisCompleted`

### 4.4 内置因子库

Wave 1 含常用技术面/基本面/情绪因子（PRD B2），作为预定义 `Factor` 实例。

---

## 5. BC6 · Market Rule（市场规则 · 多市场扩展点）

**职责**：封装各市场交易规则，供 BC3（回测）与 BC8（执行）共享；**是多市场扩展的唯一改动点**。

### 5.1 聚合根 `MarketRule`

| 项 | 内容 |
|---|---|
| 标识 | `MarketRuleId`（按市场，如 `CN_A_SHARE`） |
| 属性 | `market`, `version`, `effectiveDate` |
| 值对象 | `TradingSession`, `SettlementRule`, `PriceLimit`, `LotRule` |

**查询方法**（无副作用）：
- `isTradable(instrument, datetime)` → bool
- `checkPriceLimit(order)` → 校验涨跌停
- `settlementDays()` → T+1 / T+0 / T+2
- `nextTradeableDate(currentDate)` → 考虑 T+1 的可交易日

**不变量**：规则在 `effectiveDate` 后生效；回测/实盘引用时取快照（`MarketRuleProfile`）保证运行期间不可变。

### 5.2 值对象

- `Market`：`CN_A_SHARE` | `HK` | `US` | `FUTURES`（Wave 1 仅 `CN_A_SHARE`）
- `TradingSession`：盘前/盘中/盘后时段
- `SettlementRule`：T+N
- `PriceLimit`：涨跌停比例（A 股 10%/20%）
- `LotRule`：手数与最小变动单位（A 股 100 股/手）

### 5.3 多市场扩展契约 ⭐

> 新增市场 = 新增一个 `MarketRule` 实例 + 对应 `Instrument` 数据源，**无需改动 BC3/BC8 引擎逻辑**。

这是 PRD "架构预留多市场扩展" 在领域层的落地。Wave 3 加港股/美股时只在此上下文扩展。

### 5.4 领域事件

- `MarketRuleUpdated`（规则变更，需提示受影响历史回测可重算）

---

## 6. BC9 · Analysis & Report（绩效分析与报告）

**职责（Wave 1）**：标准绩效指标 + 归因分析。归因在 1b 子阶段实现（PRD G2）。

### 6.1 聚合根 `PerformanceReport`

| 项 | 内容 |
|---|---|
| 标识 | `PerformanceReportId` |
| 引用 | `backtestRunId`(BC3) 或 `livePortfolioId`(BC7，Wave 2) |
| 值对象 | `PerformanceMetrics`, `AttributionBreakdown` |

**命令**：
- `compute(backtestResult)` → `ReportGenerated`（标准指标）
- `computeAttribution(backtestResult)` → `AttributionCompleted`（归因）

### 6.2 值对象

**`PerformanceMetrics`**：`totalReturn`, `annualizedReturn`, `maxDrawdown`, `sharpeRatio`, `winRate`, `tradeCount`
**`AttributionBreakdown`**：Brinson/Barra 风格归因（行业/因子贡献分解）

### 6.3 领域事件

- `ReportGenerated` · `AttributionCompleted`

---

## 7. BC10 · Collaboration（社区分享 · 最小版）

**职责（Wave 1）**：策略/因子/报告的导出与导入（CLI 形态），公开浏览界面留 Wave 3。

### 7.1 聚合根 `SharedArtifact`

| 项 | 内容 |
|---|---|
| 标识 | `SharedArtifactId` |
| 属性 | `tenantId`, `ownerId`, `type`(strategy/factor/report), `refId`, `visibility` |
| 值对象 | `ArtifactSnapshot`（引用实体的只读快照，ACL） |

**命令方法**：
- `publish(ref)` → `ArtifactShared`（导出快照）
- `clone(artifactId)` → `ArtifactCloned`（导入到当前租户）

**不变量**：`ArtifactSnapshot` 为只读快照，与原实体解耦（原实体修改不影响已分享快照）。

### 7.2 领域事件

- `ArtifactShared` · `ArtifactCloned`

### 7.3 Wave 1 范围

- CLI 导出/导入（`TBD` 格式：JSON/Python 包）
- 公开社区浏览、讨论界面留 Wave 3

---

## 8. Wave 1 跨上下文契约汇总

| 契约 | 上游 → 下游 | 说明 |
|---|---|---|
| 策略代码交付 | BC2 → BC3 | `Strategy.getExecutableCode()` |
| 市场规则注入 | BC6 → BC3 | `MarketRuleProfile` 快照 |
| 数据供给 | BC4 → BC3/BC5 | `Bar` / `FundamentalRecord` 查询 |
| 因子供给 | BC5 → BC3 | `FactorResult`（策略引用因子） |
| 回测结果交付 | BC3 → BC9 | `BacktestResult` |
| 社区分享 | BC2/5/9 → BC10 | `SharedArtifact` 只读快照（ACL） |
| 执行抽象 ▶预留 | BC3 ↔ BC8 | `ExecutionEngine` 端口，Wave 2 兑现 |
| 工具 API ▶预留 | BC2/3/5/9 | OHS（Python API + 预留 HTTP），Wave 3 AI 调用 |
| `TenantId` 预留 | 全部 | 单租户默认值，Wave 3 启用多租户 |

---

## 9. Wave 1 待确认事项

- [x] **BC3 回测引擎**：双引擎——VectorEngine（简单回测，1a）+ EventEngine（复杂回测，1c）→ Wave 2 模拟/实盘。
- [ ] **BC6 规则快照粒度**：`MarketRuleProfile` 是规则全集快照还是引用 + 版本号？影响回测可复现性。
- [ ] **BC4 Instrument 主数据**：自建还是对接第三方（如 Tushare/聚源）？
- [x] **BC5 因子表达式语法**：类 WorldQuant Alpha 101 风格（具体细则待实现时定）。
- [ ] **BC10 社区分享形态**：Wave 1 的 CLI 导出/导入格式（JSON / Python 包）？
- [x] **HTTP 适配层时机**：Wave 1/2 仅预留接口，Wave 3 实现。
- [x] **`TenantId` 策略**：预留字段，单租户默认值，Wave 3 启用多租户。

---

*本文档为 Wave 1 战术设计 v0.1。确认后将作为 QuantCore + ResearchEngine 详细实现设计的输入。后续波次见 `../INIT-002-交易执行/domain-design.md` 和 `../INIT-003-AI平台/domain-design.md`。*

