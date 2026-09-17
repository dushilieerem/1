# Project Plan：经典策略迁移

| 任务 | 复杂度 | 风险 | 依赖 | 状态 |
|---|---:|---|---|---|
| RSI 规则和目录资产迁移 | 2 | 低 | FEAT-006 | 完成 |
| 事件账本持仓均价 | 2 | 中 | FEAT-006 | 完成 |
| RSI 单元与事件回归测试 | 2 | 低 | 前两项 | 完成 |
| CANSLIM 字段映射与数据审计 | 3 | 高 | FEAT-010 | 完成 |
| CANSLIM Lite | 3 | 中 | 日线收盘价、沪深 300 日线 | 完成 |
| KD 随机指标策略及测试 | 2 | 低 | 日线 OHLC、沪深300日线 | 完成 |
| 一目均衡表策略及云层位移测试 | 3 | 中 | 日线 OHLC、沪深300日线 | 完成 |
| 均线多头排列策略及日频回归测试 | 2 | 低 | 日线 OHLC、事件账本均价 | 完成 |
| 配对交易研究策略及多空权重测试 | 2 | 中 | 两只证券日线收盘价、NativeEngine | 完成 |
| Aroon 趋势策略及指标/日频回归测试 | 2 | 低 | 日线 OHLC、沪深300日线 | 完成 |
| KST 多周期动量策略及指标/日频回归测试 | 2 | 低 | 日线 OHLC、沪深300日线 | 完成 |
| 12-1 动量策略及行业相对评分回归测试 | 3 | 中 | 点时行业、成交额、日线 close | 完成 |
| 小盘价值策略及点时基本面评分回归测试 | 3 | 中 | 点时行业、成交额、PE/PB/流通市值 | 完成 |
| 红利低波狗股与三重滤网策略及日频回归测试 | 2 | 低 | 日线 OHLC、PE、股息率 | 完成 |
| 抛物线 SAR 策略及反转/日频回归测试 | 2 | 低 | 日线 OHLC、事件引擎 | 完成 |
| Fama-French/Carhart 多因子策略及面板回归测试 | 3 | 中 | 点时市值、PB、260 日 close | 完成 |
| 凯特纳通道与 Williams %R 策略及日频回归测试 | 2 | 低 | 日线 OHLC、事件引擎 | 完成 |
| 德邦特—塞勒长期反转策略及月度点时面板回归测试 | 3 | 中 | 行业、估值、市值、成交额、757 日 close | 完成 |
| 豪根—海因斯低波动异象策略及风险评分回归测试 | 3 | 中 | 行业、估值、市值、成交额、121 日 close | 完成 |
| Piotroski F-Score 会计质量策略及九项信号回归测试 | 3 | 高 | 公告日财务 TTM、PB、总市值 | 完成（策略资产；真实数据待 FEAT-010 发布） |
| 股息增长策略及连续分红事件回归测试 | 3 | 高 | 分红事件、股息率、PE、总市值 | 完成（策略资产；真实数据待 FEAT-010 发布） |
| OBV 能量潮策略、行业评分与事件回归测试 | 3 | 中 | 点时 OHLCV、成交额、行业、PE/PB、流通市值 | 完成 |
| 蔡金累积派发/振荡器策略、指标与事件回归测试 | 3 | 中 | 点时 OHLCV、成交额、行业、PE/PB、流通市值 | 完成 |
| Dual Thrust 向量化研究策略与 NativeEngine 回归测试 | 3 | 高 | 日线 OHLC、成交额、市值；盘中触发近似 | 完成（研究近似） |
| 净营运资产异象策略、NOA 公式与事件回归测试 | 3 | 高 | 点时资产负债表、PE、市值、日线 close | 完成 |
| CCI 均值回归策略、指标公式与事件回归测试 | 2 | 低 | 日线 OHLC、EventEngine | 完成 |
| MFI 资金流量策略、指标公式与字段缺失回归测试 | 2 | 中 | 日线 OHLCV、EventEngine | 完成 |
| TRIX 三重指数动量策略、信号线与事件回归测试 | 2 | 低 | 日线 OHLC、EventEngine | 完成 |
| ROC 变化率动量策略、零轴交叉与事件回归测试 | 2 | 低 | 日线 OHLC、EventEngine | 完成 |
| Ultimate Oscillator 多周期动量策略、加权公式与事件回归测试 | 2 | 低 | 日线 OHLC、EventEngine | 完成 |
| Vortex Indicator 趋势策略、VI+/VI- 公式与事件回归测试 | 2 | 低 | 日线 OHLC、EventEngine | 完成 |
| Relative Vigor Index 趋势策略、信号线与事件回归测试 | 2 | 低 | 日线 OHLC、EventEngine | 完成 |
| Elder Force Index 量价策略、成交量契约与事件回归测试 | 2 | 中 | 日线 OHLCV、EventEngine | 完成 |
| CMO 动量策略、指标公式与事件回归测试 | 2 | 低 | 日线 OHLC、EventEngine | 完成 |
| Fisher Transform 策略、信号线与事件回归测试 | 2 | 低 | 日线 OHLC、EventEngine | 完成 |
| Ease of Movement 量价策略、成交量契约与事件回归测试 | 2 | 中 | 日线 OHLCV、EventEngine | 完成 |
| Volume Price Trend 策略、成交量契约与事件回归测试 | 2 | 中 | 日线 OHLCV、EventEngine | 完成 |
| Awesome Oscillator 策略、指标公式与事件回归测试 | 2 | 低 | 日线 OHLC、EventEngine | 完成 |
| Balance of Power 策略、平滑公式与事件回归测试 | 2 | 低 | 日线 OHLC、EventEngine | 完成 |
| Choppiness Index 趋势突破策略、因果边界与事件回归测试 | 2 | 中 | 日线 OHLC、EventEngine | 完成 |
| Coppock Curve 日频研究策略、WMA 公式与事件回归测试 | 2 | 低 | 日线 OHLC、EventEngine | 完成 |
| DPO 去趋势价格振荡器策略、公式与事件回归测试 | 2 | 低 | 日线 close、EventEngine | 完成 |
| TSI 真实强度指数策略、双重平滑公式与事件回归测试 | 2 | 低 | 日线 close、EventEngine | 完成 |
| StochRSI 随机 RSI 策略、归一化公式与事件回归测试 | 2 | 低 | 日线 close、EventEngine | 完成 |
| RVI 相对波动指数策略、方向波动公式与事件回归测试 | 2 | 低 | 日线 close、EventEngine | 完成 |
| Connors RSI(2) 短期反转策略、RSI/趋势规则与事件回归测试 | 2 | 低 | 日线 close、EventEngine | 完成 |
| Supertrend 趋势策略、ATR 递推与字段契约回归测试 | 2 | 中 | 日线 OHLC、EventEngine | 完成 |
| Hull Moving Average 趋势策略、WMA/HMA 公式与事件回归测试 | 2 | 低 | 日线 close、EventEngine | 完成 |
| Williams Alligator 趋势策略、SMMA 滞后线与事件回归测试 | 2 | 中 | 日线 OHLC、EventEngine | 完成 |
| KAMA 自适应趋势策略、效率比公式与事件回归测试 | 2 | 低 | 日线 close、EventEngine | 完成 |
| McGinley Dynamic 趋势策略、递推公式与事件回归测试 | 2 | 中 | 日线 close、EventEngine | 完成 |
| Heikin-Ashi 趋势策略、蜡烛转换公式与事件回归测试 | 2 | 中 | 日线 OHLC、EventEngine | 完成 |
| Pivot Point 突破策略、前一日枢轴公式与事件回归测试 | 2 | 低 | 日线 OHLC、EventEngine | 完成 |
| 完整 CANSLIM | 5 | 高 | 公告日财务、股东数据、历史证券状态、形态金标 | 不在本 Feature 范围 |

里程碑：M1 为 RSI 可加载、可运行并通过测试；M2 为 CANSLIM Lite 只用价格数据可运行；M3 为后续 Feature 的完整 CANSLIM 通过点时数据与形态黄金样本验证。

## 本次增量任务（2026-08-20）

| 任务 | 复杂度 | 风险 | 依赖 | 状态 |
|---|---:|---|---|---|
| BBI 多空指数趋势策略、公式和目录资产 | 2 | 低 | 日线 close、EventEngine | 完成 |
| Mass Index 波动反转策略、公式和字段契约 | 2 | 中 | 日线 high/low/close、EventEngine | 完成 |
| VHF 趋势强度策略、阈值规则和目录资产 | 2 | 低 | 日线 close、EventEngine | 完成 |
| WVAD 量价趋势策略、零振幅边界和字段契约 | 2 | 中 | 日线 OHLCV、EventEngine | 完成 |
| 四策略公式、因果性、事件回测和权重边界测试 | 2 | 中 | 上述策略资产 | 完成 |

本批交付不新增 QuantCore、EventEngine 或 API 共享接口；回滚只需移除四个索引条目，源码版本保留。

## 本次增量任务（2026-08-21）

| 任务 | 复杂度 | 风险 | 依赖 | 状态 |
|---|---:|---|---|---|
| TEMA 低滞后趋势策略、公式和目录资产 | 2 | 低 | 日线 close、EventEngine | 完成 |
| SMI 随机动量策略、双重平滑公式和字段契约 | 2 | 中 | 日线 OHLC、EventEngine | 完成 |
| Ulcer Index 低回撤策略、风险公式和目录资产 | 2 | 低 | 日线 close、EventEngine | 完成 |
| Schaff Trend Cycle 趋势动量策略、双重随机公式和目录资产 | 2 | 中 | 日线 close、EventEngine | 完成 |
| 四策略公式、因果性、事件回测和权重边界测试 | 2 | 中 | 上述策略资产 | 完成 |

本批交付不新增 QuantCore、EventEngine 或 API 共享接口；回滚只需移除四个索引条目，源码版本保留。

## 本次增量任务（2026-08-24）

| 任务 | 复杂度 | 风险 | 依赖 | 状态 |
|---|---:|---|---|---|
| Elder Ray 价格力量策略、公式和目录资产 | 2 | 低 | 日线 high/low/close、EventEngine | 完成 |
| Klinger 成交量振荡器策略、成交量契约和目录资产 | 3 | 中 | 日线 high/low/close/volume、EventEngine | 完成 |
| RMI 多日动量策略、Wilder 平滑公式和目录资产 | 2 | 低 | 日线 close、EventEngine | 完成 |
| FRAMA 分形自适应趋势策略、递推公式和目录资产 | 3 | 中 | 日线 close、EventEngine | 完成 |
| 四策略公式、因果性、字段缺失、事件回测和权重边界测试 | 2 | 中 | 上述策略资产 | 完成 |

本批交付不新增 QuantCore、EventEngine 或 API 共享接口；回滚只需移除四个索引条目，源码版本保留。

## 本次增量任务（2026-08-25）

| 任务 | 复杂度 | 风险 | 依赖 | 状态 |
|---|---:|---|---|---|
| ARBR 人气意愿策略、AR/BR 公式和目录资产 | 2 | 低 | 日线 OHLC、EventEngine | 完成 |
| PSY 心理线策略、上涨广度公式和目录资产 | 2 | 低 | 日线 close、EventEngine | 完成 |
| VR 成交量比率策略、正成交量契约和目录资产 | 2 | 中 | 日线 close/volume、EventEngine | 完成 |
| VROC 成交量变动速率策略、正成交量契约和目录资产 | 2 | 低 | 日线 close/volume、EventEngine | 完成 |
| 四策略公式、因果性、字段缺失、事件回测和权重边界测试 | 2 | 中 | 上述策略资产 | 完成 |

本批交付不新增 QuantCore、EventEngine 或 API 共享接口；回滚只需移除四个索引条目，源码版本保留。
