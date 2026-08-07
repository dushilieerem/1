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
