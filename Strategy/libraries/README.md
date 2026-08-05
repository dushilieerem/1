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

## 事件策略研究候选

`appel_macd_a_share_event` 与 `bollinger_mean_reversion_a_share_event` 已迁移为 SVQuant 日频事件策略。二者仅以 OHLC 生成信号，股票池须由回测请求按历史时点准备；历史指数成分、ST 与上市状态数据接入前，均仅用于研究验证。

`wilder_rsi_classic_a_share_event` 使用 Wilder RSI(14)、200 日均线和持仓均价的 -8%/+20% 风控；日频信号按下一开盘成交。它不替代历史股票池、ST、停牌和上市状态过滤，数据面板必须先提供这些边界。

`oneil_canslim_lite_a_share_event` 是无基本面数据的 CANSLIM 研究版：只使用 250 日相对强度、简化月线基底突破和沪深 300 的 250 日均线确定满仓或半仓，并在每年首次满足数据窗口的月度调度日调仓。它不包含 C/A/I/S 因子，也不处理 ST、停牌、退市、上市天数或真正的杯柄形态。

`chande_aroon_a_share_event` 与 `pring_kst_a_share_event` 分别使用 Aroon(25) 趋势交叉和 KST(10/15/20/30 ROC) 多周期动量交叉，在沪深 300 市场过滤通过时构建最多十只、单只 9% 的现金多头组合。两者均只读取前一收盘可见的 OHLC，并于下一开盘成交；历史指数成分、ST、上市日期和交易状态由输入数据面板及事件引擎提供，因此当前仅用于研究验证。

`neff_low_pe_a_share_event` 使用 PE、盈利增速、股息率和总回报率/PE 筛选低估值价值股；`davis_double_play_a_share_event` 使用历史 PE 分位、盈利增速和 ROE 筛选价值成长股。两者均按月度调仓、最多十只等权持有，基本面字段必须由点时数据面板提供，缺失值不会自动填充。
