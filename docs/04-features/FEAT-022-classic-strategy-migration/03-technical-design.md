# Technical Design：经典策略迁移

RSI 源码位于 `Strategy/libraries/wilder_rsi_classic_a_share_event_v1.py`，通过策略目录以 `wilder_rsi_classic_a_share_event:v1` 引用。它仅依赖事件策略的 `DataView`、`PortfolioView`、`OrderService` 和调度器，不引入聚宽兼容 API。

为正确实现止盈止损，日频事件账本增加持仓 `average_cost`：买入按实际开盘成交价加权更新，全部平仓时清除；`PortfolioView.average_cost(symbol)` 只读暴露该值。策略依据截至前一日的收盘价判断风控，订单在当日开盘执行，结果明确保留日频近似假设。

CANSLIM Lite 源码位于 `Strategy/libraries/oneil_canslim_lite_a_share_event_v1.py`，只从 `DataView` 读取候选股票和沪深 300 的日线 `close`。策略每年调仓一次，按 250 日收益取前 40%，再用月末收盘价识别简化基底突破；沪深 300 高于 MA250 时使用 100% 目标暴露，否则使用 50%。它不读取或模拟公告日财务、机构持仓、流通市值或历史证券状态。简化基底突破不是严格杯柄识别。

回滚方式：从 `index.yaml` 移除对应策略条目即可停止对外引用；事件引擎均价字段为只读增量，不影响现有策略接口。

KD 策略位于 `Strategy/libraries/lane_stochastic_a_share_event_v1.py`，使用 pandas 滚动窗口计算 14/3/3 SlowK/SlowD，市场过滤只读取沪深300收盘价。其余股票池、ST、停牌、上市日期及涨跌停成交约束不在策略内模拟。

一目均衡表策略位于 `Strategy/libraries/hosoda_ichimoku_a_share_event_v1.py`。`cloud_a` 和 `cloud_b` 先将 OHLC 序列截断至 `t-26`，再计算 9/26/52 周期中点；`projected_*` 仅使用时点 `t` 已知数据。两者均通过事件 `DataView` 获得前一收盘可见数据并在日开盘成交。

均线多头排列策略位于 `Strategy/libraries/donchian_bullish_ma_alignment_a_share_event_v1.py`，默认标的为五粮液。它只读取 61 个前收盘价，在 `DataView` 提供的 as-of 快照中计算当前及前一日 MA5/10/20/60；订单在下一个交易日开盘以现金多头方式执行，持仓均价继续由事件账本只读提供。

配对交易策略位于 `Strategy/libraries/simons_pairs_trading_research_v1.py`，默认配对为贵州茅台/五粮液。它生成日频 `BacktestSignals`：每个时点的 60 日价格比仅使用截至当日的收盘价，NativeEngine 在下一日收益中使用该权重。该策略输出 ±50% 等名义多空权重；NativeEngine 当前不模拟融券、保证金和借券成本，因此目录显式标记为 `research_only`，不得视为 A 股可执行事件策略。

Aroon 与 KST 分别位于 `Strategy/libraries/chande_aroon_a_share_event_v1.py` 和 `Strategy/libraries/pring_kst_a_share_event_v1.py`。两者仅通过事件 `DataView` 读取 OHLC 和沪深 300 基准日线：Aroon 用当前日加此前 25 日的极值距离计算 Up/Down；KST 使用 10/15/20/30 日 ROC 的 10/10/10/15 日平滑、1/2/3/4 加权及 9 日信号线。策略按前一收盘生成信号、下一开盘成交，持仓上限十只、单只目标 9%。原聚宽版的历史指数成分、ST、上市日期和实时交易状态不在策略内模拟，仍由数据面板和事件引擎承载。

12-1 动量、小盘价值和红利低波狗股分别位于 `jegadeesh_titman_12_1_a_share_event_v1.py`、`fama_french_small_value_a_share_event_v1.py` 和 `dogs_of_the_dow_low_vol_a_share_event_v1.py`。前两者在月度首个交易日从前收盘可见的 `close`、`amount`、`industry` 及所需点时估值字段构建截面；行业字段必须是日期×证券面板，不能用当前行业回填历史。狗股策略仅在一月的首个交易日执行，读取前收盘的 `close`、`pe_ratio` 和 `dividend_yield`。三者均不在源码中猜测 ST、上市日期或停牌状态，停牌和涨跌停成交限制由事件引擎市场状态面板处理。

三重滤网位于 `elder_triple_screen_a_share_event_v1.py`，只读取前一收盘可见的 OHLC。策略将日线收盘重采样为周线，以周 MA5>MA10 判断趋势；KDJ 使用 9 日 RSV 及 1/3 指数平滑的 K/D，K<30 且金叉时入场。策略日频提交订单，由事件引擎在下一开盘按 A 股现金多头规则执行。

抛物线 SAR 位于 `wilder_parabolic_sar_a_share_event_v1.py`，每周一以截至前一收盘的 120 日 OHLC 计算威尔德 SAR；多头时限制 SAR 不高于前两日低点，空头时不低于前两日高点，反转日将 SAR 设为前一趋势极点。候选池按 `close/SAR-1` 排序；每日只追踪候选和持仓，出现趋势转空或收盘低于 SAR 时提交平仓订单。

Fama-French/Carhart 多因子策略位于 `fama_french_carhart_multi_factor_a_share_event_v1.py`，在每月首个交易日对截至前一收盘的点时 `market_cap`、`pb_ratio` 和 260 日 `close` 做截面评分。它不读取或估计当前财报、ST、上市天数或实时涨跌停；市值、PB 与证券状态的历史口径由上游面板负责，订单可成交性由事件引擎处理。

凯特纳通道和 Williams %R 分别位于 `keltner_channel_breakout_a_share_event_v1.py` 与 `williams_percent_r_a_share_event_v1.py`，仅通过事件 `DataView` 读取截至前一收盘的 OHLC。凯特纳通道采用 EMA20 和 Wilder ATR10；Williams %R 使用 14 日最高/最低价及 60 日趋势过滤。两者以日频订单在下一开盘成交，停牌、涨跌停与 T+1 由事件引擎统一处理。

德邦特—塞勒长期反转与豪根—海因斯低波动异象策略分别位于 `de_bondt_thaler_long_term_reversal_a_share_event_v1.py` 与 `haugen_heins_low_volatility_a_share_event_v1.py`。两者在每月首个交易日仅从 `DataView` 的前一收盘快照读取 `close`、`amount`、`industry`、`pe_ratio`、`pb_ratio` 和 `circulating_market_cap`。长期反转用 757 日价格窗口的 36-1 收益、3 个月恢复及 120 日波动率构建行业内 70%/20%/10% 得分；低波动策略用 121 日价格窗口的总波动、负收益下行波动和最大回撤构建行业内 50%/30%/20% 得分。历史行业、估值与市值必须由点时面板提供，不能以当前值回填；ST、上市时间、停牌、涨跌停和盘中调度约束不由策略源码模拟。

Piotroski F-Score 与股息增长策略分别位于 `piotroski_f_score_a_share_event_v1.py` 与 `dividend_growth_a_share_event_v1.py`。F-Score 从前一收盘可见的 `total_assets`、`total_liabilities`、`current_assets`、`current_liabilities`、`total_shares`、收入/成本/净利润/经营现金流 TTM、`pb` 和 `total_mv` 面板计算九项得分；当前值与约 90 个交易日前的点时可见值比较。股息增长从 `dividend_cash_per_share` 事件面板按自然年聚合近五年每股现金分红，并结合点时 `dividend_yield`、`pe_ttm` 和 `total_mv` 过滤。两者依赖 ADR-008 的公告日可见性，字段缺失或财务覆盖不足时不生成候选；不使用聚宽的实时证券状态或当日可成交性近似。

聂夫低市盈率策略位于 `Strategy/libraries/neff_low_pe_a_share_event_v1.py`，读取 `pe_ratio`、`dividend_yield` 和 `inc_net_profit_year_on_year` 面板字段，按 PE、盈利增速、股息率及“总回报率/PE”筛选，月度等权持有最多十只。戴维斯双击策略位于 `Strategy/libraries/davis_double_play_a_share_event_v1.py`，读取 `pe_ratio`、`roe` 和 `inc_net_profit_year_on_year`，以当前 PE 在历史面板中的分位识别低估值，并保留高估值或盈利转负退出规则。两者均不把缺失基本面填零，基本面数据的点时质量由上游数据面板负责。

本轮四个策略的源码与接口如下：

- `granville_obv_a_share_event:v1` 位于 `Strategy/libraries/granville_obv_a_share_event_v1.py`。事件策略在月度首个交易日读取前收盘可见的 `close`、`volume`、`amount`、`industry`、PE/PB 和流通市值；OBV 以收盘方向累计成交量，使用 121 日窗口和 20 日线性斜率。历史股票池、ST、停牌、上市日期和涨跌停不在源码内猜测，缺少字段即拒绝运行。
- `chaikin_accumulation_distribution_a_share_event:v1` 位于 `Strategy/libraries/chaikin_accumulation_distribution_a_share_event_v1.py`。事件策略使用前收盘可见的 OHLCV、成交额、行业、估值和流通市值，按 81 日窗口计算资金流乘数、A/D、EMA3/EMA10、CMF20 和行业评分；订单由事件引擎在下一交易日开盘成交。
- `dual_thrust_a_share:v1` 位于 `Strategy/libraries/dual_thrust_a_share_v1.py`。它采用 `BacktestSignals`，以 `open/high/low/close` 和前一日可见的成交额/市值数据生成周度候选池及日度目标权重，`NativeEngine` 使用下一交易日收益。原稿的当日 09:45 盘中价无法由当前接口读取，因此 v1 的 close-vs-open 触发是明确的研究近似，不作为实盘执行策略。
- `net_operating_assets_anomaly_a_share_event:v1` 位于 `Strategy/libraries/net_operating_assets_anomaly_a_share_event_v1.py`。事件策略按月读取不晚于前一收盘的点时资产负债表、PE、市值和价格；使用最多 260 日历史寻找最近可见的基本面值，但不向前填充或把缺失核心字段置零。回测回滚方式仍为从 `index.yaml` 移除对应条目，保留源码版本不覆盖。

本次新增的四个日频事件策略均位于 `Strategy/libraries/`，复用 `DataView.history()` 的前收盘快照、`Scheduler.daily()` 和 `OrderService.target_value()`：

- `cci_mean_reversion_a_share_event:v1` 使用 OHLC 计算典型价格、20 日 CCI 和 60 日趋势均线。
- `money_flow_index_a_share_event:v1` 使用 OHLCV 计算 14 日 MFI；`volume` 属于硬性字段依赖，缺失时在 `initialize()` 明确报错。
- `trix_momentum_a_share_event:v1` 使用 15 日三重 EMA、TRIX 和 9 日 EMA 信号线，信号仅基于前一收盘。
- `rate_of_change_momentum_a_share_event:v1` 使用 20 日 ROC 和 60 日趋势均线，输出现金多头目标市值。

四个策略不新增 QuantCore 或 EventEngine 接口，不维护策略外部状态，也不覆盖已有源码版本。回滚方式为从 `Strategy/libraries/index.yaml` 移除对应条目；源码文件保留以保证历史版本引用可追溯。

本次新增的四个日频事件策略继续复用 `DataView.history()` 的前收盘快照、`Scheduler.daily()` 和 `OrderService.target_value()`：

- `ultimate_oscillator_a_share_event:v1` 使用 7/14/28 日买压与真实波幅的加权终极振荡器，并以 60 日均线做趋势过滤。
- `vortex_indicator_a_share_event:v1` 使用 14 日正/负涡旋运动与真实波幅，比较 VI+ 和 VI- 的交叉。
- `relative_vigor_index_a_share_event:v1` 使用与既有 `technical_lib.relative_vigor_index` 相同的 4 日加权平滑，再以 4 日均线生成信号线。
- `elder_force_index_a_share_event:v1` 使用 `close.diff() * volume` 的 13 日 EMA；`volume` 是硬性字段依赖，缺失时在 `initialize()` 明确报错。

四个策略不新增 QuantCore 或 EventEngine 接口，不覆盖既有源码版本。回滚方式仍为从 `Strategy/libraries/index.yaml` 移除对应条目，源码文件保留用于历史版本追溯。

本次新增的四个日频事件策略继续复用 `DataView.history()` 的前收盘快照、`Scheduler.daily()` 和 `OrderService.target_value()`：

- `chande_momentum_oscillator_a_share_event:v1` 位于 `Strategy/libraries/chande_momentum_oscillator_a_share_event_v1.py`，使用 20 日 CMO 和 60 日趋势均线；CMO 从 -50 上穿时建立候选，零轴/50 与趋势均线负责退出。
- `fisher_transform_a_share_event:v1` 位于 `Strategy/libraries/fisher_transform_a_share_event_v1.py`，使用 10 日高低价中点的 Fisher 变换和 3 日信号线；计算中的滚动最高/最低只来自前收盘快照。
- `ease_of_movement_a_share_event:v1` 位于 `Strategy/libraries/ease_of_movement_a_share_event_v1.py`，使用 14 日 EOM；`volume` 是硬性字段依赖，箱体比率采用成交量除以 `1e8` 的 A 股日线研究尺度。
- `volume_price_trend_a_share_event:v1` 位于 `Strategy/libraries/volume_price_trend_a_share_event_v1.py`，使用标准 `close.pct_change() * volume` 累计 VPT 和 10 日 EMA 信号线；`volume` 缺失时在 `initialize()` 明确报错。

四个策略不新增 QuantCore 或 EventEngine 接口，不覆盖既有源码版本。回滚方式仍为从 `Strategy/libraries/index.yaml` 移除对应条目，源码文件保留用于历史版本追溯。

本次新增的四个日频事件策略继续复用 `DataView.history()` 的前收盘快照、`Scheduler.daily()` 和 `OrderService.target_value()`，并与 `Factor/libraries/technical_lib.py` 的既有指标口径保持一致：

- `awesome_oscillator_a_share_event:v1` 位于 `Strategy/libraries/awesome_oscillator_a_share_event_v1.py`，以中间价 SMA5-SMA34 的零轴交叉和 MA60 过滤生成信号。
- `balance_of_power_a_share_event:v1` 位于 `Strategy/libraries/balance_of_power_a_share_event_v1.py`，复用标准 BOP 公式并增加 14 日简单平滑，避免单日开收盘噪声直接触发组合订单。
- `choppiness_breakout_a_share_event:v1` 位于 `Strategy/libraries/choppiness_breakout_a_share_event_v1.py`，使用 Choppiness Index 的 38.2/61.8 阈值识别趋势/震荡环境，并以不含当前观测的前 20 日最高/最低收盘作为突破与退出边界。
- `coppock_curve_a_share_event:v1` 位于 `Strategy/libraries/coppock_curve_a_share_event_v1.py`，使用 11/14 日 ROC 和 10 日线性加权均线；该日频参数与因子库一致，是研究适配而非原始月线策略复刻。

四个源码文件均自包含，仅依赖 pandas/numpy，不修改共享 Catalog、QuantCore 或 EventEngine。字段不足在 `initialize()` 拒绝，历史不足在局部指标计算中跳过，现有持仓缺少可用指标时提交平仓；无候选时保留现金。回滚方式为从 `Strategy/libraries/index.yaml` 移除对应条目，保留 v1 源码用于历史回测追溯。
