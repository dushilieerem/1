# YGQuant 引擎详细设计

> 文档版本：v0.1（Draft · 探讨中）
> 最后更新：2026-07-07
> 维护者：YGQuant 架构组
> 状态：双引擎（VectorEngine + EventEngine）的实现设计，作为 Wave 1 代码骨架的依据。
> 关联：`03-architecture.md` §3（双引擎概览）、`02-domain/01-wave1-research-core.md`（BC3/BC5 战术设计）

---

## 1. 概述

双引擎分工：

| 引擎 | 特点 | 场景 |
|---|---|---|
| VectorEngine | 向量化矩阵运算，快 | 因子计算、因子分析、简单/快速回测 |
| EventEngine | 事件驱动，精确 | 复杂策略回测、模拟盘、实盘 |

二者均以 Python API + CLI 暴露（接口先行），Wave 3 AI 平台通过预留接口调用。

---

## 2. VectorEngine（向量化引擎）

### 2.1 技术基座

**NumPy + Pandas**（量化标配，生态成熟，社区一致）。不引入 NumExpr（维护不活跃、收益有限）。热点算子可选 **Numba JIT** 加速（可选优化，非必需）。

### 2.2 数据结构

以 DataFrame 组织，行 = 日期（DatetimeIndex），列 = 标的代码。每个字段一个 DataFrame：

```
close:        DataFrame[date × instrument]
open/high/low/volume: DataFrame[date × instrument]
factor_value: DataFrame[date × instrument]
```

多字段通过 dict 管理或宽表（MultiIndex）。

### 2.3 因子表达式引擎

Alpha 101 风格语法，自建 AST 求值器。

**流程**：源码 → 词法分析 → 语法分析（AST）→ 求值（调度到 NumPy/Pandas 向量化操作）

**算子库**（Alpha 101 标准，分三类）：
- **时序**：`delay(x,n)`, `delta(x,n)`, `ts_mean(x,n)`, `ts_std(x,n)`, `ts_rank(x,n)`, `ts_max(x,n)`
- **截面**：`rank(x)`, `scale(x)`, `zscore(x)`, `winsorize(x,n)`
- **关系**：`correlation(x,y,n)`, `covariance(x,y,n)`
- **算术**：`+ - * /`, `log`, `abs`, `decay(x,n)`

每个算子对应一个 NumPy/Pandas 向量化实现。AST 节点求值时递归调度。

```
FactorExpression (AST)
    │ evaluate(data: dict[str, DataFrame])
    ▼
FactorResult (DataFrame[date × instrument])
```

### 2.4 因子分析

均用 Pandas + NumPy 向量化：
- **IC/IR**：因子值 vs 未来收益的相关性（按日计算 IC，均值/IR）
- **分层回测**：按因子值分位数分组，计算各组累计收益
- **换手率**：因子值前后期变化率
- **相关性**：因子间相关矩阵

### 2.5 简单回测（向量化）

因子选股组合：按因子值选股 → 等权/加权组合 → 收益矩阵乘法。适合快速验证因子有效性，无需事件循环。

---

## 3. EventEngine（事件驱动引擎）

### 3.1 设计选择

**事件驱动框架，回测以 MarketEvent（bar）时间步进为主驱动，回测/实盘统一事件抽象。**

> 不采用纯 bar 驱动（实盘难适配）或纯成交驱动（回测复杂）。事件框架统一两者——bar 是其中一种事件（MarketEvent），完整事件链含 Signal/Order/Fill。

### 3.2 事件类型

| 事件 | 说明 | 产生者 |
|---|---|---|
| `MarketEvent` | 行情数据（bar/tick） | Feed（回测 HistoricalFeed / 实盘 LiveFeed） |
| `SignalEvent` | 策略产生的信号 | Strategy.on_market() |
| `OrderEvent` | 下单请求 | Portfolio.on_signal() |
| `FillEvent` | 成交回报 | ExecutionEngine.submit() |

### 3.3 事件循环

```
event_queue = PriorityQueue()   # 按时间排序
while not event_queue.empty():
    event = event_queue.pop()           # 按时间顺序
    if isinstance(event, MarketEvent):
        strategy.on_market(event)      # 策略计算信号
        → 可能 push SignalEvent
    elif isinstance(event, SignalEvent):
        portfolio.on_signal(event)     # 组合决策下单
        → 可能 push OrderEvent
    elif isinstance(event, OrderEvent):
        execution.submit(event.order)  # 撮合
        → push FillEvent
    elif isinstance(event, FillEvent):
        portfolio.on_fill(event)       # 更新持仓
```

### 3.4 回测/实盘统一

- **回测**：`HistoricalFeed` 按 bar 从历史数据生成 `MarketEvent`（时间驱动，可复现）
- **实盘**：`LiveFeed` 实时行情推送 `MarketEvent`（事件驱动）
- **EventEngine + 事件抽象不变，仅 Feed 不同**

```
Feed (Historical / Live)
   │ MarketEvent
   ▼
EventEngine 事件循环 ──► ExecutionEngine (Simulated / Live)
                            │ FillEvent
                            ▼
                        Portfolio 更新
```

### 3.5 与 ExecutionEngine 协作

- **EventEngine** 驱动事件流（按时间推进 + 触发策略/组合逻辑）
- **ExecutionEngine** 处理 `OrderEvent` 撮合 → `FillEvent`
  - `SimulatedExecutionEngine`（回测）：模拟撮合，应用 BC6 MarketRule
  - `LiveExecutionEngine`（实盘，Wave 2）：对接券商

### 3.6 MarketRule 注入

回测/实盘的 ExecutionEngine 都注入 BC6 `MarketRuleProfile`：
- **T+1**：买入当日不可卖出
- **涨跌停**：下单价格校验（A 股 10%/20%）
- **交易时段**：非时段拒绝
- **手数**：100 股整数倍

---

## 4. 双引擎协作场景

| 场景 | 引擎 | ExecutionEngine | Feed |
|---|---|---|---|
| 因子计算/分析 | VectorEngine | — | — |
| 因子选股快速回测 | VectorEngine | — | — |
| 复杂策略回测（条件单/T+1） | EventEngine | Simulated | Historical |
| 模拟盘 | EventEngine | Simulated | Live |
| 实盘（Wave 2） | EventEngine | Live | Live |

---

## 5. Wave 1 实现优先级

1. VectorEngine 基座（NumPy/Pandas 数据层 + 数据加载）
2. 因子表达式引擎（AST + 算子库）
3. 因子分析（IC/IR/分层）
4. EventEngine 事件循环 + 事件类型
5. `SimulatedExecutionEngine` + BC6 MarketRule（A 股规则）
6. 简单回测（VectorEngine）→ 复杂策略回测（EventEngine）

---

## 6. 待确认事项

- [ ] **数据存储格式**：Parquet / HDF5 / 数据库？影响数据加载性能。
- [ ] **算子库范围**：Alpha 101 全量 vs. 常用子集首期？
- [ ] **事件循环并发模型**：同步队列 vs. asyncio？影响实盘行情处理。
- [ ] **回测并发**：多回测并行执行？关联 BC12 配额（Wave 3）。
- [ ] **Numba 加速范围**：哪些热点算子需要 JIT？
- [ ] **策略 API 形态**：`Strategy` 基类回调（on_market/on_fill）vs. 函数式？

---

*本文档为 v0.1 探讨稿。随 Wave 1 实现推进深化。*
