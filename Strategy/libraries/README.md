# 策略库

本目录保存项目级、可复现的策略源码；每次修改策略逻辑时新增一个 `.py` 版本文件，禁止覆盖已被回测引用的版本。

`index.yaml` 是唯一索引。每个策略必须声明业务 `strategy_type`（如 `trend`、`momentum`、`reversal`、`small_cap`）、执行 `execution_mode`（`vectorized` 或 `event`）、`current_version` 与 `versions`；每个版本声明源码文件和策略类入口。

```yaml
version: 2
strategies:
  weekly_rotation:
    name: 周度轮动
    strategy_type: momentum
    execution_mode: vectorized
    current_version: v1
    tags: [轮动]
    versions:
      v1:
        file: weekly_rotation_v1.py
        entrypoint: WeeklyRotationStrategy
```

当前 `vectorized` 策略必须遵守 `/api/backtest/strategy` 的 `generate_signals()` 契约。`event` 条目可提前登记，但要等事件驱动回测 API 交付后才能运行。

## 内置可回测策略

以下七个策略仅依赖日线 `close` 面板，可通过当前向量化回测直接运行；它们用于研究和示例，不构成投资建议。

| 策略 ID | 逻辑 | 数据依赖 |
|---|---|---|
| `ma_13_26_maotai` | 贵州茅台 13/26 日均线满仓/空仓 | `close`（含 `600519.SH`） |
| `dual_moving_average` | 20/60 日均线趋势，多头等权 | `close` |
| `cross_sectional_momentum` | 20 日动量最高的 Top10 | `close` |
| `short_term_reversal` | 5 日收益最低的 Top10 | `close` |
| `low_volatility` | 20 日收益波动最低的 Top10 | `close` |
| `donchian_breakout` | 创 60 日新高的标的等权持有 | `close` |
| `markowitz_min_variance` | 60/120 日正动量预筛后，按 120 日协方差构建月度最小方差组合 | `close`；仅研究用途，使用请求传入的静态股票池 |

`markowitz_min_variance` 的 v1 不模拟动态指数成分、ST/停牌/涨跌停和盘中订单执行，也不代表完整的 A 股实盘策略；这些能力将在数据与事件回测条件具备后以新版本补齐。
