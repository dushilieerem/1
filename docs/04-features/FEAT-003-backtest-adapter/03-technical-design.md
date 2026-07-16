# 回测适配层设计

> 文档版本：v0.1
> 最后更新：2026-07-13
> 关联：`../../05-architecture/system_architecture.md` §3（双引擎）、`../../05-architecture/engine-design.md`、`../../03-portfolio/initiatives/INIT-001-research-core/domain-design.md` BC3
> 状态：已落地（Native + VectorBT 双后端）

---

## 1. 动机

把回测做成「适配层 + 可插拔后端」：

```
ResearchEngine（公共 API、因子代码不变）
        │  Experiment.run() 委托给适配器（config 选后端，默认 native）
QuantCore
        │  领域接口（6 个）：
        ├─ IStrategy      generate_signals() -> 目标权重信号
        ├─ IDataFeed      行情面板来源（= DataEngine）
        ├─ IPortfolio     组合状态契约（事件引擎用）
        ├─ IExecution     撮合/成本契约（事件引擎用）
        ├─ ICalendar      交易日/调仓日历
        ├─ IMetrics       (= MetricEngine)
        ▼
IBacktestEngine  ← 适配器契约：run(signals, config) -> BacktestResult
        │
 ┌──────┴──────────┐
 │                 │
VectorBTEngine   NativeEngine
(wraps vectorbt) (提炼自 build_factor_portfolio，行为等价)
```

**收益**：今天 `Strategy ↓ VectorBT`，明天 `Strategy ↓ 自研引擎`，ResearchEngine 无感--切后端 = 改一行 config。

---

## 2. 六个领域接口

| 接口 | 职责 | 在两后端中的角色 | 位置 |
|---|---|---|---|
| `IStrategy` | 策略产出向量化信号（目标权重 `日期×标的`） | **共享主契约**（两后端都吃） | `adapter/interfaces.py` |
| `IDataFeed` | 行情面板来源 | 共享输入（= 现有 `DataEngine`/`IDataProvider`） | 同上 |
| `ICalendar` | 交易日 / 调仓日历 | 策略与事件引擎用 | 同上 |
| `IPortfolio` | 组合状态（现金/持仓/盯市） | 事件引擎可插拔件；向量化后端**内化** | 同上 |
| `IExecution` | 撮合 / 成本 | 事件引擎可插拔件；向量化后端**内化** | 同上 |
| `IMetrics` | 指标计算（`Protocol`） | 共享输出消费方（= `MetricEngine`） | 同上 |

**诚实说明**：vectorbt 是单体向量化库，无法拆成 `IDataFeed`/`IPortfolio`/`IExecution` 可插拔件。
因此向量化后端（Native / VectorBT）只遵守顶层 `IBacktestEngine.run(signals, config)` 契约，
内化 portfolio/execution/calendar；`IPortfolio`/`IExecution`/`ICalendar` 是**事件驱动自研引擎**
（未来 EventEngine）的组件契约，本次仅形式化定义（现有 `Portfolio`/`MatchingEngine` 作为虚拟子类满足）。

---

## 3. IStrategy 契约（向量化信号）

```python
class IStrategy(ABC):
    def generate_signals(self, panel: Panel | None = None) -> BacktestSignals: ...
```

`BacktestSignals` 主字段 `target_weights: DataFrame[日期×标的]`：

- `NaN` = 无目标/不持有（供 `ffill` 持有至下一调仓日）；
- 其余为该日期望权重（多头正、空头负）。

**为什么是向量化、不是 bar 回调**：vectorbt 只能跑向量化信号/权重数组，跑不了 `on_bar -> orders`。
事件驱动策略（现有 `BacktestEngine` demo 的 `strategy_func(bar, portfolio) -> List[Order]`）
留待未来 EventEngine（Wave 1 1c），不在本适配器。

内置实现 `FactorQuantileStrategy`：每个调仓日按因子值截面排名，做多 top `stock_num`、
（可选）做空 bottom `stock_num`，等权。提炼自原 `build_factor_portfolio` 的因子->权重逻辑。

---

## 4. 两后端

### NativeEngine（`adapter/native_engine.py`）

逐字复刻 `build_factor_portfolio` 的净值数学：

```python
held   = target.ffill().shift(1).fillna(0.0)   # t 收盘调仓，t+1 起持有
port_ret = (held * ret).sum(axis=1).iloc[1:].dropna()
equity = 1.0 + port_ret.cumsum()               # 固定本金口径
```

- 默认 `cost=0` -> 与 `build_factor_portfolio` **逐位等价**（`test_native_engine_parity_with_build_factor_portfolio` 护栏）。
- `cost>0` 时按换手率 `|Δheld|` 计入手续费/滑点（原 `build_factor_portfolio` 不扣成本，属增强）。

### VectorBTEngine（`adapter/vectorbt_engine.py`）

懒加载 `vectorbt`，把 `target_weights` 透传给：

```python
vbt.Portfolio.from_orders(
    close, target_weights,
    size_type="targetpercent", group_by=True, cash_sharing=True,
    init_cash=..., fees=commission_rate, slippage=slippage_rate, freq="1D",
)
```

取 `pf.returns()` 去 NaN 后 `1 + cumsum`，与 Native 口径同构。

---

## 5. 成本与口径（已知差异）

| 项 | Native | VectorBT |
|---|---|---|
| 默认成本 | 0（与历史等价） | 0 |
| 手续费率 | `commission_rate`（换手×率） | `fees`（vectorbt 透传） |
| **每笔最低手续费** `min_commission` | ✅ 支持 | ❌ 原生不支持，按比例近似 |
| 滑点 | `slippage_rate` | `slippage` |
| 净值口径 | `1.0 + cumsum`（固定本金） | `pf.value()` 归一化为 `1.0` 基 |
| 撮合时序 | `shift(1)`（信号 t 收盘 -> t+1 持有） | vectorbt 默认当 bar 成交，存在 1 bar 偏差 |

故两后端**不逐位相等**，仅「同方向、同量级」接近：
`test_native_vs_vectorbt_parity` 断言相关系数 > 0.95、终值相对误差 < 5%。

---

## 6. 如何加第三个后端

1. 实现 `IBacktestEngine`：
   ```python
   class MyEngine(IBacktestEngine):
       name = "my_engine"
       def run(self, signals, config) -> BacktestResult: ...
   ```
2. 在 `adapter/registry.py` 注册（或仿照 `vectorbt` 懒加载分支）。
3. `config.yaml` 设 `backtest.engine: my_engine`。

ResearchEngine、因子代码、指标层**零改动**。

---

## 7. 用法

```python
from quantcore import FactorQuantileStrategy, get_backtest_engine, BacktestConfig

strategy = FactorQuantileStrategy(factor_values, close,
                                  rebalance="monthly", stock_num=100, long_short=True)
signals = strategy.generate_signals()
cfg = BacktestConfig(engine="vectorbt", commission_rate=0.0003, slippage_rate=0.001)
result = get_backtest_engine(cfg.engine).run(signals, cfg)
# result.equity_curve / result.returns / result.positions -> MetricContext
```

或在 `ResearchEngine/config.yaml`：

```yaml
backtest:
  engine: native      # native | vectorbt
  initial_capital: 1000000
  commission_rate: 0.0003
  slippage_rate: 0.001
```

---

## 8. 与现有代码的关系

- `ResearchEngine/portfolio.py::build_factor_portfolio` 改为**薄包装**，委托 `NativeEngine + FactorQuantileStrategy`，返回同 `(equity, returns, positions)` 元组。导出与外部调用方不变。
- `Experiment.run()` 改走适配器（默认 `native` -> 数值与现状逐位一致）。
- 事件驱动 `BacktestEngine` / `MatchingEngine` / `Order` / `Fill` / `Portfolio` / `TransactionCost` **原样保留**（仅 `Portfolio`/`MatchingEngine` 虚拟子类化满足 `IPortfolio`/`IExecution`），作为未来 EventEngine 基座；`test_backtest.py` 仍绿。
- `BacktestResult` 扩展：`portfolio` 改 `Optional`，新增 `returns`/`positions` 字段（`__post_init__` 派生 returns，访问名不变）。

---

## 9. 环境

- 项目 Conda 环境（Python 3.13.14）已装 `vectorbt 1.1.0`（会自动降 numpy 至 2.4.6）。
- vectorbt 为可选依赖：`pip install -e ".[vectorbt]"`。未装时平台与 NativeEngine 照常工作；仅 `get_backtest_engine("vectorbt").run(...)` 时报清晰安装提示。
