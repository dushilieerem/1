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

`jegadeesh_titman_12_1_a_share_event` 使用行业内 12-1/6-1 动量和低波动评分；`fama_french_small_value_a_share_event` 使用行业内低 PB、低 PE 与小流通市值评分。两者都要求点时的行业、流动性和基本面面板。`dogs_of_the_dow_low_vol_a_share_event` 每年一月按高股息前 30% 内的低波动筛选；`elder_triple_screen_a_share_event` 以周 MA5/10、日线 KDJ(9,3,3) 实现三重滤网。四者均为日频本地研究资产，并不替代历史证券状态或数据质量校验。

`wilder_parabolic_sar_a_share_event` 使用威尔德标准 SAR 递推、按多头安全边际每周构建候选池，并在日频反转时退出。`fama_french_carhart_multi_factor_a_share_event` 以小市值、低 PB 与 12-1 动量作月度截面评分；其市值和 PB 必须是点时面板，不能使用最新快照回填历史。

`keltner_channel_breakout_a_share_event` 使用 EMA20 与 Wilder ATR10 的两倍构建通道，在上轨突破时入场；`williams_percent_r_a_share_event` 在 60 日趋势向上时，以 14 日 %R 的超卖上穿构建反转信号。两者均只适用于日频研究，并由事件引擎处理开盘成交及 A 股可成交性约束。

`piotroski_f_score_a_share_event` 在低 PB 股票中以九项会计质量信号筛选月度组合；`dividend_growth_a_share_event` 要求连续五年现金分红且最近一年不降，并在中等股息率股票中选股。两者均依赖公告日点时财务数据；后者还依赖逐笔 `dividend_cash_per_share` 分红事件。数据版本未发布这些字段时会明确拒绝运行，当前仅用于研究验证。

`granville_obv_a_share_event` 使用收盘方向累计成交量、20 日标准化斜率和行业评分；`chaikin_accumulation_distribution_a_share_event` 使用资金流乘数、A/D、EMA3/EMA10 和 CMF20。两者均为月度事件策略，依赖前收盘可见的 OHLCV、成交额、行业、估值和流通市值面板，缺少字段时拒绝运行。

`dual_thrust_a_share` 使用前 N 日波动区间和当日开盘锚定上下轨生成向量化目标权重，并按周更新流动性候选池。原始策略的 09:45 盘中信号在 v1 中近似为当日收盘信号，结果仅用于研究验证。

`net_operating_assets_anomaly_a_share_event` 使用点时资产负债表计算 NOA/总资产，按月度 NOA 升序构建组合；核心字段缺失时不以零值填充。

`cci_mean_reversion_a_share_event`、`money_flow_index_a_share_event`、`trix_momentum_a_share_event` 和 `rate_of_change_momentum_a_share_event` 是新增的日频事件研究策略，分别使用 CCI、MFI、TRIX 和 ROC 生成现金多头信号。四者均按前一收盘计算、下一交易日开盘成交；MFI 额外要求 `volume` 字段。它们不补造盘中价格、历史成分或市场状态，结果仅用于研究验证。

`ultimate_oscillator_a_share_event`、`vortex_indicator_a_share_event`、`relative_vigor_index_a_share_event` 和 `elder_force_index_a_share_event` 是本次新增的日频事件研究策略，分别使用 Ultimate Oscillator、Vortex Indicator、RVI 和 Elder Force Index 生成现金多头信号。四者均按前一收盘计算、下一交易日开盘成交；Elder Force Index 额外要求 `volume` 字段，结果仅用于研究验证。

`chande_momentum_oscillator_a_share_event`、`fisher_transform_a_share_event`、`ease_of_movement_a_share_event` 和 `volume_price_trend_a_share_event` 是本次新增的日频事件研究策略，分别使用 CMO、Fisher Transform、EOM 和标准 VPT 生成现金多头信号。四者均按前一收盘计算、下一交易日开盘成交；EOM 与 VPT 额外要求 `volume` 字段，结果仅用于研究验证。

`awesome_oscillator_a_share_event`、`balance_of_power_a_share_event`、`choppiness_breakout_a_share_event` 和 `coppock_curve_a_share_event` 是本次新增的日频事件研究策略，分别使用 AO、14 日平滑 BOP、Choppiness Index 配合 20 日突破和 Coppock Curve 生成现金多头信号。四者只依赖日频 OHLC，均按前一收盘计算、下一交易日开盘成交；最多持有十只、单只目标 9%。当前版本不包含动态历史股票池、ST、停牌或盘中成交近似，结果仅用于研究验证。

`dpo_mean_reversion_a_share_event`、`true_strength_index_a_share_event`、`stoch_rsi_a_share_event` 和 `relative_volatility_index_a_share_event` 是本批新增的日频事件研究策略，分别使用 DPO、TSI、StochRSI 和 RVI 生成现金多头信号。四者只声明并读取 `close` 字段；事件引擎仍需标准 OHLC 面板以完成开盘成交。信号均按前一收盘计算、下一交易日开盘成交，最多持有十只、单只目标 9%。DPO 使用 20 日去趋势价格振荡器和 MA60，TSI 使用 25/13 双重平滑与 9 日信号线，StochRSI 使用 14/14 参数，RVI 使用 10 日波动率和 14 日平滑。当前版本不包含动态历史股票池、ST、停牌或盘中成交近似，结果仅用于研究验证。

`connors_rsi2_a_share_event`、`supertrend_a_share_event`、`hull_moving_average_a_share_event` 和 `williams_alligator_a_share_event` 是本批新增的日频事件研究策略，分别使用 Connors RSI(2)、Supertrend、Hull Moving Average 和 Williams Alligator 生成现金多头信号。RSI(2) 与 HMA 只声明并读取 `close`；Supertrend 与 Alligator 声明并读取 `high`、`low`、`close`。四者均按前一收盘生成信号、下一交易日开盘成交，最多持有十只、单只目标 9%。Connors RSI(2) 使用 MA200 趋势过滤和 MA5/RSI 阈值退出；Supertrend 使用 Wilder ATR10、3 倍波动带和 MA60 过滤；HMA 使用 20 日 WMA 组合和 MA60 过滤；Alligator 使用 13/8/5 日 SMMA 的 8/5/3 日滞后线。当前版本不模拟盘中触发、动态历史成分股、ST/停牌/涨跌停之外的策略专属过滤，结果仅用于研究验证。

`kaufman_adaptive_moving_average_a_share_event`、`mcginley_dynamic_a_share_event`、`heikin_ashi_trend_a_share_event` 和 `pivot_point_breakout_a_share_event` 是 2026-08-19 新增的日频事件研究策略，分别使用 KAMA、McGinley Dynamic、Heikin-Ashi 和 Pivot Point 生成现金多头信号。KAMA 与 McGinley Dynamic 只声明并读取 `close`；Heikin-Ashi 声明完整 `open/high/low/close`，Pivot Point 声明 `high/low/close`。四者均按前一收盘生成信号、下一交易日开盘成交，最多持有十只、单只目标 9%；前两者使用 MA60 趋势过滤，Heikin-Ashi 使用多头 HA 蜡烛，Pivot Point 使用前一交易日的枢轴阻力突破。当前版本不模拟盘中触发、动态历史成分股、ST/停牌/涨跌停之外的策略专属过滤，结果仅用于研究验证。

`bbi_trend_a_share_event`、`mass_index_reversal_a_share_event`、`vhf_trend_a_share_event` 和 `wvad_volume_trend_a_share_event` 是 2026-08-20 新增的日频事件研究策略，分别使用 BBI、Mass Index、VHF 和 WVAD 生成现金多头信号。BBI 只声明 `close`，使用 SMA3/6/12/24 的平均值并配合 MA60 趋势过滤；Mass Index 声明 `high`、`low`、`close`，使用 9 日区间均值比率的 25 日累计值，在指标从 27 以上扩张后回落至 26.5 以下且价格高于 MA60 时入场；VHF 只声明 `close`，以 28 日价格区间与绝对变动总和衡量趋势强度，0.4 上穿入场、0.3 下破退出；WVAD 声明完整 OHLCV，使用 24 日 `(close-open)/(high-low)*volume` 累计量价推动，零振幅日按零资金流处理。四者均按前一收盘生成信号、下一交易日开盘成交，最多持有十只、单只目标 9%；当前版本不模拟盘中触发、动态历史成分股、ST/停牌/涨跌停之外的策略专属过滤，结果仅用于研究验证。

`triple_exponential_moving_average_a_share_event`、`stochastic_momentum_index_a_share_event`、`ulcer_index_low_drawdown_a_share_event` 和 `schaff_trend_cycle_a_share_event` 是 2026-08-21 新增的日频事件研究策略，分别使用 TEMA、SMI、Ulcer Index 和 Schaff Trend Cycle 生成现金多头信号。TEMA 与 Ulcer Index 只声明 `close`；SMI 声明 `high`、`low`、`close`；STC 只声明 `close`。TEMA 使用 20 日三重 EMA 和 MA60 趋势过滤；SMI 使用 14 日区间、双重 3 日平滑和 3 日信号线；Ulcer Index 使用 14 日滚动回撤风险并在指标回落至 5 以下时入场；STC 使用 23/50 日 MACD、10 日周期和双重 3 日随机平滑。四者均按前一收盘生成信号、下一交易日开盘成交，最多持有十只、单只目标 9%；当前版本不模拟盘中触发、动态历史股票池、ST、停牌或涨跌停之外的策略专属过滤，结果仅用于研究验证。

`elder_ray_index_a_share_event`、`klinger_volume_oscillator_a_share_event`、`relative_momentum_index_a_share_event` 和 `fractal_adaptive_moving_average_a_share_event` 是 2026-08-24 新增的日频事件研究策略，分别使用 Elder Ray 牛力/熊力、Klinger 风格成交量振荡器、RMI 多日动量和 FRAMA 分形自适应均线生成现金多头信号。Elder Ray 声明 `high/low/close`；Klinger 声明 `high/low/close/volume`；RMI 与 FRAMA 只声明并读取 `close`。四者均按前一收盘生成信号、下一交易日开盘成交，最多持有十只、单只目标 9%；缺少声明字段、历史不足或指标无效时拒绝运行或不下单，当前版本不模拟盘中触发、动态历史股票池、ST、停牌或涨跌停之外的策略专属过滤，结果仅用于研究验证。

`arbr_sentiment_a_share_event`、`psy_sentiment_a_share_event`、`volume_ratio_a_share_event` 和 `volume_rate_of_change_a_share_event` 是 2026-08-25 新增的日频事件研究策略，分别使用 ARBR 人气意愿差、PSY 心理线、VR 成交量比率和 VROC 成交量变动速率生成现金多头信号。ARBR 声明完整 OHLC；PSY 只声明 `close`；VR 与 VROC 声明 `close/volume`。ARBR 使用 26 日 AR/BR 与 MA60 趋势过滤，PSY 使用 12 日上涨交易日占比，VR 使用 26 日上涨/下跌/盘整成交量比率，VROC 使用 12 日成交量变动速率；四者均按前一收盘生成信号、下一交易日开盘成交，最多持有十只、单只目标 9%。缺少声明字段、历史不足、无有效价格或最新成交量非正时不生成候选，当前版本不模拟盘中触发、动态历史股票池、ST、停牌或涨跌停之外的策略专属过滤，结果仅用于研究验证。
