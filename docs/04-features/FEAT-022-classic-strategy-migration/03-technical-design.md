# Technical Design：经典策略迁移

RSI 源码位于 `Strategy/libraries/wilder_rsi_classic_a_share_event_v1.py`，通过策略目录以 `wilder_rsi_classic_a_share_event:v1` 引用。它仅依赖事件策略的 `DataView`、`PortfolioView`、`OrderService` 和调度器，不引入聚宽兼容 API。

为正确实现止盈止损，日频事件账本增加持仓 `average_cost`：买入按实际开盘成交价加权更新，全部平仓时清除；`PortfolioView.average_cost(symbol)` 只读暴露该值。策略依据截至前一日的收盘价判断风控，订单在当日开盘执行，结果明确保留日频近似假设。

CANSLIM Lite 源码位于 `Strategy/libraries/oneil_canslim_lite_a_share_event_v1.py`，只从 `DataView` 读取候选股票和沪深 300 的日线 `close`。策略每年调仓一次，按 250 日收益取前 40%，再用月末收盘价识别简化基底突破；沪深 300 高于 MA250 时使用 100% 目标暴露，否则使用 50%。它不读取或模拟公告日财务、机构持仓、流通市值或历史证券状态。简化基底突破不是严格杯柄识别。

回滚方式：从 `index.yaml` 移除对应策略条目即可停止对外引用；事件引擎均价字段为只读增量，不影响现有策略接口。

KD 策略位于 `Strategy/libraries/lane_stochastic_a_share_event_v1.py`，使用 pandas 滚动窗口计算 14/3/3 SlowK/SlowD，市场过滤只读取沪深300收盘价。其余股票池、ST、停牌、上市日期及涨跌停成交约束不在策略内模拟。

一目均衡表策略位于 `Strategy/libraries/hosoda_ichimoku_a_share_event_v1.py`。`cloud_a` 和 `cloud_b` 先将 OHLC 序列截断至 `t-26`，再计算 9/26/52 周期中点；`projected_*` 仅使用时点 `t` 已知数据。两者均通过事件 `DataView` 获得前一收盘可见数据并在日开盘成交。

均线多头排列策略位于 `Strategy/libraries/donchian_bullish_ma_alignment_a_share_event_v1.py`，默认标的为五粮液。它只读取 61 个前收盘价，在 `DataView` 提供的 as-of 快照中计算当前及前一日 MA5/10/20/60；订单在下一个交易日开盘以现金多头方式执行，持仓均价继续由事件账本只读提供。

配对交易策略位于 `Strategy/libraries/simons_pairs_trading_research_v1.py`，默认配对为贵州茅台/五粮液。它生成日频 `BacktestSignals`：每个时点的 60 日价格比仅使用截至当日的收盘价，NativeEngine 在下一日收益中使用该权重。该策略输出 ±50% 等名义多空权重；NativeEngine 当前不模拟融券、保证金和借券成本，因此目录显式标记为 `research_only`，不得视为 A 股可执行事件策略。
