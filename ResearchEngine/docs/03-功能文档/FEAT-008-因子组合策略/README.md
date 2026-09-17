# FEAT-008：结构化因子组合策略

- 状态：已完成
- 所属 Initiative：INIT-001 投研核心
- 所属能力：策略研究、策略回测

让用户以 Python 类定义因子函数、组合信号、Top-N、权重和调仓周期，系统编译为现有向量化回测使用的目标权重矩阵。

## 1. 价值与范围

### 背景

现有因子回测只支持单因子和平台固定的组合构建，现有策略回测则要求用户手写完整的 `generate_signals()`。两者之间缺少一种适合大多数研究员、可读且可校验的多因子组合策略表达。

### MVP

用户在 `FactorPortfolioStrategy` 子类中用 `@factor` 编写与因子回测相同的面板因子函数，用唯一 `@signal` 函数通过 Python 运算组合因子；系统支持 `TopN`、`EqualWeight`、`EveryNTradingDays` 并复用现有向量化后端。

不做：事件驱动回测、行业/单票约束、因子资产持久化、Python AST 沙箱或任意权重器。

### 价值

用户看到 Python 而非 YAML；平台仍可识别策略的结构化组件，并保持因子研究的快速向量化执行能力。

## 2. 业务规则与场景

### 用户流程

前端提交 `FactorPortfolioStrategy` 源码 → ResearchEngine 加载策略 → 因子函数基于行情面板计算 → `@signal` 输出综合分数 → `TopN` 选股、`EqualWeight` 配权、按调仓周期输出目标权重 → 现有回测后端执行。

### 业务规则

- 策略必须且只能声明一个 `@signal` 方法；它必须返回日期 × 标的的分数宽表。
- `@factor` 方法和因子回测一样可访问 `self.close`、`self.volume`、`self.pe_ttm` 等字段。
- `rank`、`zscore`、`winsorize`、`normalize` 按日横截面计算，用于因子组合前的量纲处理。
- `TopN(n)` 仅选取分数最高的 `n` 个有效标的；`EqualWeight` 对入选标的等权；非调仓日输出 `NaN` 以沿用上一期目标仓位。

### 验收标准

1. 两个 `@factor` 和一个 `@signal` 的策略可经 `/api/backtest/strategy` 成功回测。
2. `@signal` 中的因子函数可相加、相乘并调用标准化函数。
3. 没有或有多个 `@signal` 时返回清晰错误。
4. `TopN`、等权和每 N 日调仓的目标权重符合单元测试断言。
5. 原有 `generate_signals()` 策略 API 与测试不退化。
6. Web 请求传入 `include_rebalance_logs=true` 时，返回按调仓日聚合、仅含权重变化标的的目标调仓日志；未传时不返回该数据。

## 3. 方案设计

新增 `quantcore.backtest.adapter.factor_strategy`：

```python
class FactorPortfolioStrategy(FactorLibrary, IStrategy):
    selector = TopN(30)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(20)
```

`@factor` 和 `@signal` 仅标记方法；执行时把 `Panel` 绑定到 `FactorLibrary`，调用唯一 signal 方法取得分数，再转换为 `BacktestSignals`。不新增第二套因子表达式语言。

ResearchEngine 在策略类为 `FactorPortfolioStrategy` 子类时传入已加载的 `Panel`；其他策略维持现有 `factor_values/close/params` 构造与 `generate_signals()` 契约。该选择保证向后兼容。

测试覆盖信号校验、横截面处理、目标权重、API 端到端和既有 API 回归。回滚方式为移除新策略类的使用；现有端点和后端不变。

策略回测后端基于目标权重矩阵生成统一调仓日志，记录调仓信号日、标的、买卖方向和调整前后权重。ResearchEngine 仅在请求的 `include_rebalance_logs=true` 时把日志返回给 Web，默认不序列化，保持既有响应体大小和兼容性。日志描述目标权重变更，不替代未来事件驱动引擎的订单/成交回报。

## 4. 验收与证据

### 验证记录

- 验证日期：2026-07-21
- 状态：通过

| 验收项 | 验证结果 |
|---|---|
| 多个 `@factor` 与唯一 `@signal` 可回测 | API 端到端测试通过。 |
| 因子函数可组合并使用横截面处理 | 单元测试覆盖 `rank`、`zscore`、`normalize`。 |
| Top-N、等权、每 N 日调仓正确 | 单元测试验证权重和调仓日 `NaN` 语义。 |
| `@signal` 缺失时清晰失败 | 单元测试验证错误信息。 |
| 原策略回测兼容 | ResearchEngine API 全部测试通过。 |

验证命令：

```bash
D:\Devtools\anaconda3\envs\svquant\python.exe -m pytest -q
```

结果：`106 passed, 1 warning`。唯一 warning 来自 FastAPI 测试客户端依赖的弃用提示，与本 Feature 无关。

## 5. 计划与里程碑

| 任务 | 复杂度 | 风险 | 验证 |
|---|---:|---|---|
| 实现策略 DSL 与组合信号编译 | 3 | 中 | QuantCore 单元测试 |
| 接入 ResearchEngine 策略运行器 | 2 | 低 | API 端到端测试 |
| 补充 API/策略编写文档 | 1 | 低 | 示例与实现一致 |
| 回归测试 | 2 | 低 | 全量 pytest |

里程碑：M1 策略类生成权重；M2 API 可运行；M3 全量测试通过并记录验证。
