# SVQuant 全量因子 Alpha101 逻辑分析

> 生成时间：2026-08-20T03:58:25.179472+00:00
> 目录版本：1；目录更新时间：2026-08-19
> 当前范围：13 个因子库、1055 个因子
> 分析性质：源码约束下的语义解释，不包含 IC、收益、回测或实盘结论。

## 1. 分析范围与证据级别

本报告每次运行重新读取以下三类资料：

- Factor/libraries/index.yaml：登记名称、参数、描述和库级治理元数据。
- Factor/libraries/：可执行因子源码，作为字段、窗口、算子和未来数据判断的主要事实来源。
- Factor/因子库总览.md：人工维护的库级背景和语义补充，用于交叉核对。

事实优先级为：源码 > index.yaml > 因子库总览.md。当前三方目录校验结果如下：

- 源码与 index.yaml：ok
- index.yaml 与因子库总览.md：ok
- 未登记源码文件：0
- 源码解析错误：0
- 差异明细：当前未发现。

输入文件指纹：

- index.yaml：SHA256=5e62643afdb33456fc97dfe92b54869665b308bb5b5cf195655e25da362b850a；更新时间=2026-08-19T02:53:56.292135+00:00
- 因子库总览.md：SHA256=c0af51e9007779c9da9ab94d2de4e62f9127cec449e53451f44882e93b86b840；更新时间=2026-08-19T02:50:52.594017+00:00
- 源码文件数：13

源码快照（相对路径 / 更新时间 / SHA256）：

| 源码文件 | 更新时间 | SHA256 |
|---|---|---|
| Factor/libraries/alpha_features.py | 2026-07-24T11:15:37.031662+00:00 | aca241752d2812b1b519005e4a147ad098565eaa27bf23b1326a7bd2b09625c7 |
| Factor/libraries/alpha_library.py | 2026-07-17T04:04:10.112297+00:00 | a9584559bcaacbaaa43c916c97a467d6677af2b406611b87fcd5a6b3ea6dd4a3 |
| Factor/libraries/classic_indicators.py | 2026-08-10T07:18:21.011518+00:00 | be2dc37a3aeb915dc01b8d355f22c88b71800d3d797bd38a421906c1951f5bdd |
| Factor/libraries/emotion_indicators.py | 2026-07-24T11:15:37.031662+00:00 | 62c0d63ed9e556aee004c3581f2a80e1b62b60ece402bec6d8e01ff9248ba746 |
| Factor/libraries/gtja_alpha191.py | 2026-08-14T10:01:09.947757+00:00 | 187ace050e7e039786d51809aa149692123369a639fe9eabbc0d86a9fe271cf7 |
| Factor/libraries/momentum_lib.py | 2026-07-28T02:26:50.975299+00:00 | c5b846e21e7e5b09190f9fb81dc376ab6de0e6e108bc738cbe5111dba7623653 |
| Factor/libraries/risk_indicators.py | 2026-07-24T11:15:37.033655+00:00 | 35d57f39b3bbe218dd03c522e49ef5cf791dbf3dfb3c77c01261286c5f32314f |
| Factor/libraries/technical_indicators.py | 2026-07-24T11:15:37.034652+00:00 | b6e811269eff72ec340393e1b7e540260e9ad3454a7c41655fc8fc251d1523a2 |
| Factor/libraries/technical_lib.py | 2026-08-18T02:22:09.473077+00:00 | ff2c5adab6c50b161bed5b6527eb33c42c28837e32f4817b218cb56178131e0e |
| Factor/libraries/trading_lib.py | 2026-08-07T05:15:07.086548+00:00 | 41797a681e37d4d559f3ac4d5b75c8a6001aaee4602bd2af21af28186e93aadd |
| Factor/libraries/value_lib.py | 2026-07-17T04:04:10.118815+00:00 | b918d3cc6957e5095f1ddef18e65bb9e91b9b99f53dedf0cd140f9a6f50e374e |
| Factor/libraries/volatility_lib.py | 2026-08-19T02:48:45.903741+00:00 | 226fcaeba0a1f3637f671c15edf3c9b61c6800cf73cc6aaa6077ee276eba4ddc |
| Factor/libraries/worldquant_alpha101.py | 2026-08-10T10:07:13.459411+00:00 | c0cf83dfeb1ab9847b3274a138d679354d431feb048c7bfdce64cd47412627f1 |

## 2. Alpha101 分析框架

参考 Coriva 的 Alpha101 文章，将 WorldQuant Alpha101 按量价背离、动量与反转、波动率、日内结构、流动性与复合五类逻辑解释；其他因子库在此基础上补充价值/估值、规模、风险分布、特征工程和标签/不可交易等扩展分类。

文章来源：[WorldQuant Alpha 101 全解读：因子分类与算子速查](https://coriva.eu.org/alpha101-overview/)。文章强调 rank 是横截面比较，delay/delta/ts_rank/correlation/decay_linear 等算子表达时间序列位置、变化、联动和近期加权；本报告将这些算子解释与 SVQuant 源码实际回退口径分开记录。

| 文章分类 | 文章口径因子数 | 主要问题 |
|---|---:|---|
| 量价背离 | 32 | 价格与成交信息是否同步 |
| 动量与反转 | 23 | 趋势延续还是短期过度反应 |
| 波动率 | 11 | 风险状态是否切换或回归 |
| 日内结构 | 12 | OHLC/VWAP 的同日相对位置 |
| 流动性与复合 | 23 | 成交活跃度是否确认价格变化 |

### 当前全库主分类初稿统计

下表是基于源码字段、算子、库域和模板参数生成的全库主分类初稿，不代表因子有效性；WorldQuant Alpha101 条目优先采用文章来源逐因子表。

| 主分类 | 当前因子数 |
|---|---:|
| 动量与反转 | 464 |
| 流动性与复合 | 163 |
| 待复核 | 137 |
| 日内结构 | 113 |
| 量价背离 | 96 |
| 波动率与风险分布 | 40 |
| 波动率 | 26 |
| 价值/估值或规模 | 15 |
| 标签/不可交易 | 1 |

## 3. 全库重点发现

- 当前共发现 810 个动态生成或动态包装因子；Alpha158/Alpha360、Alpha101 和 Alpha191 均不能只靠类内静态方法列表解释。
- 当前源码检测到 18 个含行业/分组中性化或相关字段的因子；文章来源对 Alpha101 的概览口径为 26 个，当前实现检测口径为 18 个，需在后续逐条核对中区分“文章标记”和“SVQuant 实际调用”。
- 检测到 1 个未来数据候选：alpha_library/futureRes。这些条目只能作为标签或事后评价对象。
- Alpha101 #42、#54 等只使用当日 OHLC/VWAP 的结构因子需要特别标注 A 股 T+1 时点；当前报告不把它们直接描述为可交易信号。
- 对任何因子，源码中的最终符号、排名、条件分支和中性化都会改变直觉方向；“大值代表什么”不等同于“应该做多什么”。

## 4. 按主分类的完整分析

主分类是报告的分析主线；因子库不再单独成章，只在每个因子条目中作为来源描述。多因子公式族使用三级标题、成员用加粗名称列出；只有单因子公式族才使用因子名作为三级标题。相同公式的不同参数先在公式族层面合并解释，再保留独立因子条目记录参数和来源差异。

## 动量与反转

> 因子数量：464；来源分布：alpha_features 404、worldquant_alpha101 23、momentum_lib 18、technical_lib 10、classic_indicators 5、alpha_library 3、technical_indicators 1

趋势延续还是短期过度反应。短窗口通常用反转假设解释，中等窗口则常用信息扩散和趋势延续解释。 短期反转来自获利了结、流动性冲击和超卖后的修复；中期动量来自信息逐步扩散、资金分批交易和趋势跟随。条件分支会先判断当前处于单边趋势还是震荡状态，再选择动量或反转表达。

常见表达是 returns/pct_change、delta、delay/shift、ts_rank、ts_min/ts_max 和条件分支；窗口长度决定观察周期，外层负号、排名和乘积决定最终方向。 不能把所有动量因子理解为做多强势股，也不能把所有反转因子理解为买入弱势股。Alpha#9 的重点是趋势状态判断，Alpha#20 的重点是跳空位置与回补假设，必须结合最终公式的符号和输入位置解读。

Alpha#9 在连续上涨/下跌时用时间序列排名衡量当前变化在窗口中的位置，在涨跌交替时转向反转结构；Alpha#20 用开盘价相对前一日 high/close/low 的位置捕捉跳空后的回补假设。

边界上，窗口过短容易受到交易噪声和涨跌停影响，窗口过长又可能混入市场状态变化。A 股 T+1、复权方式和预热区间会直接影响 delay、delta 和 rolling 结果。

### Alpha158 BETA 公式族（5 个参数变体）

这组因子的共同公式是 `rolling_apply(close, {window}, linear_slope) / close`。共同输入字段为 close，主要算子为 rolling_apply、linear_slope；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_beta5、alpha158_beta10、alpha158_beta20、alpha158_beta30、alpha158_beta60。

**因子：alpha158_beta5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性斜率、动态生成
- 本条参数差异：沿用上述“Alpha158 BETA 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 rolling_apply、linear_slope；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 BETA5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7027、7033
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_beta10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性斜率、动态生成
- 本条参数差异：沿用上述“Alpha158 BETA 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 rolling_apply、linear_slope；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 BETA10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7037、7043
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_beta20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性斜率、动态生成
- 本条参数差异：沿用上述“Alpha158 BETA 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 rolling_apply、linear_slope；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 BETA20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7047、7053
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_beta30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性斜率、动态生成
- 本条参数差异：沿用上述“Alpha158 BETA 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 rolling_apply、linear_slope；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 BETA30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7057、7063
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_beta60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性斜率、动态生成
- 本条参数差异：沿用上述“Alpha158 BETA 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 rolling_apply、linear_slope；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 BETA60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7067、7073
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 CNTD 公式族（5 个参数变体）

这组因子的共同公式是 `rolling(up_count, {window}).mean() - rolling(down_count, {window}).mean()`。共同输入字段为 close，主要算子为 shift、rolling、mean、conditional；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_cntd5、alpha158_cntd10、alpha158_cntd20、alpha158_cntd30、alpha158_cntd60。

**因子：alpha158_cntd5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTD 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTD5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7827、7833
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cntd10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTD 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTD10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7837、7843
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cntd20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTD 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTD20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7847、7853
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cntd30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTD 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTD30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7857、7863
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cntd60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTD 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTD60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7867、7873
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 CNTN 公式族（5 个参数变体）

这组因子的共同公式是 `rolling((close - close.shift(1) < 0), {window}).mean()`。共同输入字段为 close，主要算子为 shift、rolling、mean、conditional；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_cntn5、alpha158_cntn10、alpha158_cntn20、alpha158_cntn30、alpha158_cntn60。

**因子：alpha158_cntn5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTN 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTN5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7777、7783
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cntn10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTN 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTN10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7787、7793
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cntn20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTN 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTN20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7797、7803
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cntn30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTN 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTN30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7807、7813
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cntn60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTN 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTN60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7817、7823
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 CNTP 公式族（5 个参数变体）

这组因子的共同公式是 `rolling((close - close.shift(1) > 0), {window}).mean()`。共同输入字段为 close，主要算子为 shift、rolling、mean、conditional；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_cntp5、alpha158_cntp10、alpha158_cntp20、alpha158_cntp30、alpha158_cntp60。

**因子：alpha158_cntp5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTP 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTP5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7727、7733
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cntp10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTP 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTP10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7737、7743
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cntp20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTP 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTP20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7747、7753
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cntp30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTP 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTP30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7757、7763
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cntp60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、均值、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 CNTP 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 shift、rolling、mean、conditional；窗口 shift=1、rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CNTP60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7767、7773
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha158_high0
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、动态生成、字段回退
- 计算结构：字段 high、close；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha158 HIGH0。
- 源码计算片段：共享模板具体公式：high / close
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close、high、low、open、volume 的log、滚动窗口、历史位移、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 high、close 的近期变化、历史位置或极值位置转成强弱信号；差分/滚动窗口 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 high、close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：Alpha158 HIGH0。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6843、6849
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 IMAX 公式族（5 个参数变体）

这组因子的共同公式是 `rolling_apply(high, {window}, argmax + 1) / {window}`。共同输入字段为 high，主要算子为 rolling_apply、argmax；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_imax5、alpha158_imax10、alpha158_imax20、alpha158_imax30、alpha158_imax60。

**因子：alpha158_imax5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、滚动函数、argmax、动态生成
- 本条参数差异：沿用上述“Alpha158 IMAX 公式族”；本因子参数为 window=5。
- 计算结构：字段 high；算子 rolling_apply、argmax；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMAX5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7477、7483
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_imax10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、滚动函数、argmax、动态生成
- 本条参数差异：沿用上述“Alpha158 IMAX 公式族”；本因子参数为 window=10。
- 计算结构：字段 high；算子 rolling_apply、argmax；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMAX10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7487、7493
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_imax20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、滚动函数、argmax、动态生成
- 本条参数差异：沿用上述“Alpha158 IMAX 公式族”；本因子参数为 window=20。
- 计算结构：字段 high；算子 rolling_apply、argmax；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMAX20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7497、7503
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_imax30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、滚动函数、argmax、动态生成
- 本条参数差异：沿用上述“Alpha158 IMAX 公式族”；本因子参数为 window=30。
- 计算结构：字段 high；算子 rolling_apply、argmax；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMAX30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7507、7513
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_imax60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、滚动函数、argmax、动态生成
- 本条参数差异：沿用上述“Alpha158 IMAX 公式族”；本因子参数为 window=60。
- 计算结构：字段 high；算子 rolling_apply、argmax；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMAX60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7517、7523
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 IMIN 公式族（5 个参数变体）

这组因子的共同公式是 `rolling_apply(low, {window}, argmin + 1) / {window}`。共同输入字段为 low，主要算子为 rolling_apply、argmin；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_imin5、alpha158_imin10、alpha158_imin20、alpha158_imin30、alpha158_imin60。

**因子：alpha158_imin5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、滚动函数、argmin、动态生成
- 本条参数差异：沿用上述“Alpha158 IMIN 公式族”；本因子参数为 window=5。
- 计算结构：字段 low；算子 rolling_apply、argmin；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMIN5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7527、7533
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_imin10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、滚动函数、argmin、动态生成
- 本条参数差异：沿用上述“Alpha158 IMIN 公式族”；本因子参数为 window=10。
- 计算结构：字段 low；算子 rolling_apply、argmin；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMIN10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7537、7543
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_imin20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、滚动函数、argmin、动态生成
- 本条参数差异：沿用上述“Alpha158 IMIN 公式族”；本因子参数为 window=20。
- 计算结构：字段 low；算子 rolling_apply、argmin；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMIN20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7547、7553
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_imin30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、滚动函数、argmin、动态生成
- 本条参数差异：沿用上述“Alpha158 IMIN 公式族”；本因子参数为 window=30。
- 计算结构：字段 low；算子 rolling_apply、argmin；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMIN30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7557、7563
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_imin60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、滚动函数、argmin、动态生成
- 本条参数差异：沿用上述“Alpha158 IMIN 公式族”；本因子参数为 window=60。
- 计算结构：字段 low；算子 rolling_apply、argmin；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMIN60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7567、7573
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 IMXD 公式族（5 个参数变体）

这组因子的共同公式是 `(rolling_apply(high, {window}, argmax + 1) - rolling_apply(low, {window}, argmin + 1)) / {window}`。共同输入字段为 high、low，主要算子为 rolling_apply、argmax、argmin；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_imxd5、alpha158_imxd10、alpha158_imxd20、alpha158_imxd30、alpha158_imxd60。

**因子：alpha158_imxd5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、low、滚动函数、argmax、argmin、动态生成
- 本条参数差异：沿用上述“Alpha158 IMXD 公式族”；本因子参数为 window=5。
- 计算结构：字段 high、low；算子 rolling_apply、argmax、argmin；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high、low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMXD5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7577、7583
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_imxd10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、low、滚动函数、argmax、argmin、动态生成
- 本条参数差异：沿用上述“Alpha158 IMXD 公式族”；本因子参数为 window=10。
- 计算结构：字段 high、low；算子 rolling_apply、argmax、argmin；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high、low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMXD10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7587、7593
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_imxd20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、low、滚动函数、argmax、argmin、动态生成
- 本条参数差异：沿用上述“Alpha158 IMXD 公式族”；本因子参数为 window=20。
- 计算结构：字段 high、low；算子 rolling_apply、argmax、argmin；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high、low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMXD20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7597、7603
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_imxd30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、low、滚动函数、argmax、argmin、动态生成
- 本条参数差异：沿用上述“Alpha158 IMXD 公式族”；本因子参数为 window=30。
- 计算结构：字段 high、low；算子 rolling_apply、argmax、argmin；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high、low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMXD30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7607、7613
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_imxd60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、low、滚动函数、argmax、argmin、动态生成
- 本条参数差异：沿用上述“Alpha158 IMXD 公式族”；本因子参数为 window=60。
- 计算结构：字段 high、low；算子 rolling_apply、argmax、argmin；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high、low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 IMXD60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7617、7623
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha158_klow2
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、high、low、close、逐点最大值、逐点最小值、动态生成、字段回退
- 计算结构：字段 open、high、low、close；算子 maximum、minimum；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha158 KLOW2。
- 源码计算片段：共享模板具体公式：(minimum(open, close) - low) / (high - low + EPSILON)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close、high、low、open、volume 的log、滚动窗口、历史位移、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 open、high、low、close 的近期变化、历史位置或极值位置转成强弱信号；逐点最大值、逐点最小值 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 open、high、low、close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：Alpha158 KLOW2。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6803、6809
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha158_kmid2
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、high、low、close、动态生成、字段回退
- 计算结构：字段 open、high、low、close；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha158 KMID2。
- 源码计算片段：共享模板具体公式：(close - open) / (high - low + EPSILON)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close、high、low、open、volume 的log、滚动窗口、历史位移、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 open、high、low、close 的近期变化、历史位置或极值位置转成强弱信号；差分/滚动窗口 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 open、high、low、close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：Alpha158 KMID2。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6763、6769
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha158_ksft2
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、low、close、动态生成、字段回退
- 计算结构：字段 high、low、close；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha158 KSFT2。
- 源码计算片段：共享模板具体公式：(2 * close - high - low) / (high - low + EPSILON)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close、high、low、open、volume 的log、滚动窗口、历史位移、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 high、low、close 的近期变化、历史位置或极值位置转成强弱信号；差分/滚动窗口 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 high、low、close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：Alpha158 KSFT2。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6823、6829
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha158_kup2
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、high、low、close、逐点最大值、逐点最小值、动态生成、字段回退
- 计算结构：字段 open、high、low、close；算子 maximum、minimum；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha158 KUP2。
- 源码计算片段：共享模板具体公式：(high - maximum(open, close)) / (high - low + EPSILON)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close、high、low、open、volume 的log、滚动窗口、历史位移、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 open、high、low、close 的近期变化、历史位置或极值位置转成强弱信号；逐点最大值、逐点最小值 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 open、high、low、close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：Alpha158 KUP2。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6783、6789
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha158_low0
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、动态生成、字段回退
- 计算结构：字段 low、close；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha158 LOW0。
- 源码计算片段：共享模板具体公式：low / close
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close、high、low、open、volume 的log、滚动窗口、历史位移、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 low、close 的近期变化、历史位置或极值位置转成强弱信号；差分/滚动窗口 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 low、close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：Alpha158 LOW0。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6853、6859
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 MA 公式族（5 个参数变体）

这组因子的共同公式是 `close.rolling({window}, min_periods=1).mean() / close`。共同输入字段为 close，主要算子为 rolling、mean；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_ma5、alpha158_ma10、alpha158_ma20、alpha158_ma30、alpha158_ma60。

**因子：alpha158_ma5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 MA 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 rolling、mean；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MA5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6927、6933
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_ma10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 MA 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 rolling、mean；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MA10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6937、6943
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_ma20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 MA 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 rolling、mean；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MA20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6947、6953
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_ma30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 MA 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 rolling、mean；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MA30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6957、6963
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_ma60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 MA 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 rolling、mean；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MA60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6967、6973
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 MAX 公式族（5 个参数变体）

这组因子的共同公式是 `high.rolling({window}, min_periods=1).max() / close`。共同输入字段为 high、close，主要算子为 rolling、max；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_max5、alpha158_max10、alpha158_max20、alpha158_max30、alpha158_max60。

**因子：alpha158_max5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、滚动窗口、滚动最大值、动态生成
- 本条参数差异：沿用上述“Alpha158 MAX 公式族”；本因子参数为 window=5。
- 计算结构：字段 high、close；算子 rolling、max；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MAX5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7177、7183
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_max10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、滚动窗口、滚动最大值、动态生成
- 本条参数差异：沿用上述“Alpha158 MAX 公式族”；本因子参数为 window=10。
- 计算结构：字段 high、close；算子 rolling、max；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MAX10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7187、7193
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_max20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、滚动窗口、滚动最大值、动态生成
- 本条参数差异：沿用上述“Alpha158 MAX 公式族”；本因子参数为 window=20。
- 计算结构：字段 high、close；算子 rolling、max；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MAX20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7197、7203
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_max30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、滚动窗口、滚动最大值、动态生成
- 本条参数差异：沿用上述“Alpha158 MAX 公式族”；本因子参数为 window=30。
- 计算结构：字段 high、close；算子 rolling、max；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MAX30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7207、7213
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_max60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、滚动窗口、滚动最大值、动态生成
- 本条参数差异：沿用上述“Alpha158 MAX 公式族”；本因子参数为 window=60。
- 计算结构：字段 high、close；算子 rolling、max；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MAX60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7217、7223
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 MIN 公式族（5 个参数变体）

这组因子的共同公式是 `low.rolling({window}, min_periods=1).min() / close`。共同输入字段为 low、close，主要算子为 rolling、min；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_min5、alpha158_min10、alpha158_min20、alpha158_min30、alpha158_min60。

**因子：alpha158_min5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、滚动窗口、滚动最小值、动态生成
- 本条参数差异：沿用上述“Alpha158 MIN 公式族”；本因子参数为 window=5。
- 计算结构：字段 low、close；算子 rolling、min；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MIN5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7227、7233
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_min10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、滚动窗口、滚动最小值、动态生成
- 本条参数差异：沿用上述“Alpha158 MIN 公式族”；本因子参数为 window=10。
- 计算结构：字段 low、close；算子 rolling、min；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MIN10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7237、7243
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_min20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、滚动窗口、滚动最小值、动态生成
- 本条参数差异：沿用上述“Alpha158 MIN 公式族”；本因子参数为 window=20。
- 计算结构：字段 low、close；算子 rolling、min；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MIN20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7247、7253
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_min30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、滚动窗口、滚动最小值、动态生成
- 本条参数差异：沿用上述“Alpha158 MIN 公式族”；本因子参数为 window=30。
- 计算结构：字段 low、close；算子 rolling、min；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MIN30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7257、7263
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_min60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、滚动窗口、滚动最小值、动态生成
- 本条参数差异：沿用上述“Alpha158 MIN 公式族”；本因子参数为 window=60。
- 计算结构：字段 low、close；算子 rolling、min；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 MIN60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7267、7273
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha158_open0
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、动态生成、字段回退
- 计算结构：字段 open、close；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha158 OPEN0。
- 源码计算片段：共享模板具体公式：open / close
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close、high、low、open、volume 的log、滚动窗口、历史位移、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 open、close 的近期变化、历史位置或极值位置转成强弱信号；差分/滚动窗口 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 open、close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：Alpha158 OPEN0。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6833、6839
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 QTLD 公式族（5 个参数变体）

这组因子的共同公式是 `close.rolling({window}, min_periods=1).quantile(0.2) / close`。共同输入字段为 close，主要算子为 rolling、quantile；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_qtld5、alpha158_qtld10、alpha158_qtld20、alpha158_qtld30、alpha158_qtld60。

**因子：alpha158_qtld5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、分位数、动态生成
- 本条参数差异：沿用上述“Alpha158 QTLD 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 rolling、quantile；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 QTLD5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7327、7333
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_qtld10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、分位数、动态生成
- 本条参数差异：沿用上述“Alpha158 QTLD 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 rolling、quantile；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 QTLD10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7337、7343
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_qtld20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、分位数、动态生成
- 本条参数差异：沿用上述“Alpha158 QTLD 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 rolling、quantile；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 QTLD20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7347、7353
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_qtld30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、分位数、动态生成
- 本条参数差异：沿用上述“Alpha158 QTLD 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 rolling、quantile；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 QTLD30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7357、7363
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_qtld60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、分位数、动态生成
- 本条参数差异：沿用上述“Alpha158 QTLD 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 rolling、quantile；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 QTLD60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7367、7373
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 QTLU 公式族（5 个参数变体）

这组因子的共同公式是 `close.rolling({window}, min_periods=1).quantile(0.8) / close`。共同输入字段为 close，主要算子为 rolling、quantile；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_qtlu5、alpha158_qtlu10、alpha158_qtlu20、alpha158_qtlu30、alpha158_qtlu60。

**因子：alpha158_qtlu5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、分位数、动态生成
- 本条参数差异：沿用上述“Alpha158 QTLU 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 rolling、quantile；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 QTLU5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7277、7283
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_qtlu10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、分位数、动态生成
- 本条参数差异：沿用上述“Alpha158 QTLU 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 rolling、quantile；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 QTLU10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7287、7293
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_qtlu20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、分位数、动态生成
- 本条参数差异：沿用上述“Alpha158 QTLU 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 rolling、quantile；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 QTLU20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7297、7303
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_qtlu30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、分位数、动态生成
- 本条参数差异：沿用上述“Alpha158 QTLU 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 rolling、quantile；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 QTLU30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7307、7313
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_qtlu60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、分位数、动态生成
- 本条参数差异：沿用上述“Alpha158 QTLU 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 rolling、quantile；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 QTLU60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7317、7323
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 RANK 公式族（5 个参数变体）

这组因子的共同公式是 `close.rolling({window}, min_periods=1).rank(pct=True)`。共同输入字段为 close，主要算子为 rolling、rank；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_rank5、alpha158_rank10、alpha158_rank20、alpha158_rank30、alpha158_rank60。

**因子：alpha158_rank5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、截面排名、动态生成
- 本条参数差异：沿用上述“Alpha158 RANK 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 rolling、rank；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RANK5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7377、7383
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_rank10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、截面排名、动态生成
- 本条参数差异：沿用上述“Alpha158 RANK 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 rolling、rank；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RANK10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7387、7393
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_rank20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、截面排名、动态生成
- 本条参数差异：沿用上述“Alpha158 RANK 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 rolling、rank；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RANK20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7397、7403
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_rank30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、截面排名、动态生成
- 本条参数差异：沿用上述“Alpha158 RANK 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 rolling、rank；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RANK30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7407、7413
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_rank60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、截面排名、动态生成
- 本条参数差异：沿用上述“Alpha158 RANK 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 rolling、rank；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RANK60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7417、7423
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 RESI 公式族（5 个参数变体）

这组因子的共同公式是 `rolling_apply(close, {window}, linear_residual) / close`。共同输入字段为 close，主要算子为 rolling_apply、linear_residual；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_resi5、alpha158_resi10、alpha158_resi20、alpha158_resi30、alpha158_resi60。

**因子：alpha158_resi5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性残差、动态生成
- 本条参数差异：沿用上述“Alpha158 RESI 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 rolling_apply、linear_residual；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RESI5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7127、7133
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_resi10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性残差、动态生成
- 本条参数差异：沿用上述“Alpha158 RESI 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 rolling_apply、linear_residual；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RESI10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7137、7143
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_resi20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性残差、动态生成
- 本条参数差异：沿用上述“Alpha158 RESI 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 rolling_apply、linear_residual；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RESI20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7147、7153
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_resi30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性残差、动态生成
- 本条参数差异：沿用上述“Alpha158 RESI 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 rolling_apply、linear_residual；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RESI30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7157、7163
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_resi60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性残差、动态生成
- 本条参数差异：沿用上述“Alpha158 RESI 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 rolling_apply、linear_residual；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RESI60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7167、7173
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 ROC 公式族（5 个参数变体）

这组因子的共同公式是 `close.shift({window}) / close`。共同输入字段为 close，主要算子为 shift；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_roc5、alpha158_roc10、alpha158_roc20、alpha158_roc30、alpha158_roc60。

**因子：alpha158_roc5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha158 ROC 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 shift；窗口 shift=1、rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 ROC5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6877、6883
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_roc10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha158 ROC 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 shift；窗口 shift=1、rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 ROC10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6887、6893
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_roc20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha158 ROC 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 shift；窗口 shift=1、rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 ROC20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6897、6903
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_roc30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha158 ROC 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 shift；窗口 shift=1、rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 ROC30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6907、6913
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_roc60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha158 ROC 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 shift；窗口 shift=1、rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 ROC60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6917、6923
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 RSQR 公式族（5 个参数变体）

这组因子的共同公式是 `rolling_apply(close, {window}, linear_rsquare)`。共同输入字段为 close，主要算子为 rolling_apply、linear_rsquare；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_rsqr5、alpha158_rsqr10、alpha158_rsqr20、alpha158_rsqr30、alpha158_rsqr60。

**因子：alpha158_rsqr5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性拟合优度、动态生成
- 本条参数差异：沿用上述“Alpha158 RSQR 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 rolling_apply、linear_rsquare；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RSQR5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7077、7083
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_rsqr10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性拟合优度、动态生成
- 本条参数差异：沿用上述“Alpha158 RSQR 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 rolling_apply、linear_rsquare；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RSQR10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7087、7093
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_rsqr20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性拟合优度、动态生成
- 本条参数差异：沿用上述“Alpha158 RSQR 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 rolling_apply、linear_rsquare；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RSQR20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7097、7103
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_rsqr30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性拟合优度、动态生成
- 本条参数差异：沿用上述“Alpha158 RSQR 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 rolling_apply、linear_rsquare；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RSQR30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7107、7113
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_rsqr60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动函数、线性拟合优度、动态生成
- 本条参数差异：沿用上述“Alpha158 RSQR 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 rolling_apply、linear_rsquare；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RSQR60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7117、7123
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 RSV 公式族（5 个参数变体）

这组因子的共同公式是 `(close - low.rolling({window}, min_periods=1).min()) / (high.rolling({window}, min_periods=1).max() - low.rolling({window}, min_periods=1).min() + EPSILON)`。共同输入字段为 close、high、low，主要算子为 rolling、min、max；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_rsv5、alpha158_rsv10、alpha158_rsv20、alpha158_rsv30、alpha158_rsv60。

**因子：alpha158_rsv5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、high、low、滚动窗口、滚动最小值、滚动最大值、动态生成
- 本条参数差异：沿用上述“Alpha158 RSV 公式族”；本因子参数为 window=5。
- 计算结构：字段 close、high、low；算子 rolling、min、max；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、high、low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RSV5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7427、7433
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_rsv10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、high、low、滚动窗口、滚动最小值、滚动最大值、动态生成
- 本条参数差异：沿用上述“Alpha158 RSV 公式族”；本因子参数为 window=10。
- 计算结构：字段 close、high、low；算子 rolling、min、max；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、high、low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RSV10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7437、7443
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_rsv20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、high、low、滚动窗口、滚动最小值、滚动最大值、动态生成
- 本条参数差异：沿用上述“Alpha158 RSV 公式族”；本因子参数为 window=20。
- 计算结构：字段 close、high、low；算子 rolling、min、max；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、high、low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RSV20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7447、7453
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_rsv30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、high、low、滚动窗口、滚动最小值、滚动最大值、动态生成
- 本条参数差异：沿用上述“Alpha158 RSV 公式族”；本因子参数为 window=30。
- 计算结构：字段 close、high、low；算子 rolling、min、max；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、high、low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RSV30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7457、7463
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_rsv60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、high、low、滚动窗口、滚动最小值、滚动最大值、动态生成
- 本条参数差异：沿用上述“Alpha158 RSV 公式族”；本因子参数为 window=60。
- 计算结构：字段 close、high、low；算子 rolling、min、max；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、high、low；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 RSV60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7467、7473
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 SUMD 公式族（5 个参数变体）

这组因子的共同公式是 `(positive_sum - negative_sum) / rolling(abs(close - close.shift(1)), {window}).sum()`。共同输入字段为 close，主要算子为 shift、rolling、sum、conditional；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_sumd5、alpha158_sumd10、alpha158_sumd20、alpha158_sumd30、alpha158_sumd60。

**因子：alpha158_sumd5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMD 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMD5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7977、7983
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_sumd10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMD 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMD10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7987、7993
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_sumd20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMD 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMD20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7997、8003
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_sumd30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMD 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMD30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8007、8013
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_sumd60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMD 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMD60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8017、8023
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 SUMN 公式族（5 个参数变体）

这组因子的共同公式是 `rolling(negative(close - close.shift(1)), {window}).sum() / rolling(abs(close - close.shift(1)), {window}).sum()`。共同输入字段为 close，主要算子为 shift、rolling、sum、conditional；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_sumn5、alpha158_sumn10、alpha158_sumn20、alpha158_sumn30、alpha158_sumn60。

**因子：alpha158_sumn5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMN 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMN5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7927、7933
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_sumn10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMN 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMN10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7937、7943
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_sumn20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMN 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMN20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7947、7953
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_sumn30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMN 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMN30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7957、7963
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_sumn60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMN 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMN60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7967、7973
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 SUMP 公式族（5 个参数变体）

这组因子的共同公式是 `rolling(positive(close - close.shift(1)), {window}).sum() / rolling(abs(close - close.shift(1)), {window}).sum()`。共同输入字段为 close，主要算子为 shift、rolling、sum、conditional；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_sump5、alpha158_sump10、alpha158_sump20、alpha158_sump30、alpha158_sump60。

**因子：alpha158_sump5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMP 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMP5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7877、7883
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_sump10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMP 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMP10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7887、7893
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_sump20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMP 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMP20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7897、7903
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_sump30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMP 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMP30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7907、7913
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_sump60**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 SUMP 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 SUMP60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7917、7923
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha158_vwap0
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、成交量加权价格、动态生成、字段回退
- 计算结构：字段 vwap、close；算子 vwap；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha158 VWAP0。
- 源码计算片段：共享模板具体公式：vwap / close
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close、high、low、open、volume 的log、滚动窗口、历史位移、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 vwap、close 的近期变化、历史位置或极值位置转成强弱信号；成交量加权价格 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 vwap、close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：Alpha158 VWAP0。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6863、6869
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha360 CLOSE 公式族（60 个参数变体）

这组因子的共同公式是 `close.shift({day}) / close`。共同输入字段为 close，主要算子为 shift；参数梯度为 day ∈ {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59}。

族级解读：day 只改变回看距离，字段决定比较的是价格还是成交量；它们不是彼此独立的 360 种经济逻辑。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha360_close0、alpha360_close1、alpha360_close2 … alpha360_close57、alpha360_close58、alpha360_close59（共 60 个）。

**因子：alpha360_close0**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=0。
- 计算结构：字段 close；算子 shift；窗口 shift=0；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族并取 day=0，形成当前值与当前值自身的基准比；day 增大后才逐步引入更远历史观测点。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE0。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3141、3147
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close1**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=1。
- 计算结构：字段 close；算子 shift；窗口 shift=1；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=1；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE1。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3151、3157
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close2**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=2。
- 计算结构：字段 close；算子 shift；窗口 shift=2；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=2；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE2。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3161、3167
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close3**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=3。
- 计算结构：字段 close；算子 shift；窗口 shift=3；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=3；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE3。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3171、3177
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close4**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=4。
- 计算结构：字段 close；算子 shift；窗口 shift=4；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=4；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE4。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3181、3187
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=5。
- 计算结构：字段 close；算子 shift；窗口 shift=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=5；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3191、3197
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close6**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=6。
- 计算结构：字段 close；算子 shift；窗口 shift=6；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=6；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE6。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3201、3207
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close7**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=7。
- 计算结构：字段 close；算子 shift；窗口 shift=7；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=7；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE7。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3211、3217
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close8**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=8。
- 计算结构：字段 close；算子 shift；窗口 shift=8；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=8；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE8。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3221、3227
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close9**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=9。
- 计算结构：字段 close；算子 shift；窗口 shift=9；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=9；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE9。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3231、3237
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=10。
- 计算结构：字段 close；算子 shift；窗口 shift=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=10；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3241、3247
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close11**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=11。
- 计算结构：字段 close；算子 shift；窗口 shift=11；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=11；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE11。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3251、3257
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close12**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=12。
- 计算结构：字段 close；算子 shift；窗口 shift=12；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=12；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE12。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3261、3267
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close13**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=13。
- 计算结构：字段 close；算子 shift；窗口 shift=13；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=13；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE13。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3271、3277
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close14**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=14。
- 计算结构：字段 close；算子 shift；窗口 shift=14；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=14；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE14。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3281、3287
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close15**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=15。
- 计算结构：字段 close；算子 shift；窗口 shift=15；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=15；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE15。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3291、3297
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close16**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=16。
- 计算结构：字段 close；算子 shift；窗口 shift=16；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=16；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE16。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3301、3307
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close17**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=17。
- 计算结构：字段 close；算子 shift；窗口 shift=17；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=17；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE17。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3311、3317
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close18**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=18。
- 计算结构：字段 close；算子 shift；窗口 shift=18；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=18；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE18。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3321、3327
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close19**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=19。
- 计算结构：字段 close；算子 shift；窗口 shift=19；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=19；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE19。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3331、3337
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=20。
- 计算结构：字段 close；算子 shift；窗口 shift=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=20；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3341、3347
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close21**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=21。
- 计算结构：字段 close；算子 shift；窗口 shift=21；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=21；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE21。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3351、3357
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close22**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=22。
- 计算结构：字段 close；算子 shift；窗口 shift=22；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=22；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE22。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3361、3367
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close23**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=23。
- 计算结构：字段 close；算子 shift；窗口 shift=23；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=23；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE23。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3371、3377
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close24**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=24。
- 计算结构：字段 close；算子 shift；窗口 shift=24；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=24；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE24。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3381、3387
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close25**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=25。
- 计算结构：字段 close；算子 shift；窗口 shift=25；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=25；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE25。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3391、3397
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close26**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=26。
- 计算结构：字段 close；算子 shift；窗口 shift=26；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=26；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE26。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3401、3407
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close27**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=27。
- 计算结构：字段 close；算子 shift；窗口 shift=27；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=27；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE27。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3411、3417
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close28**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=28。
- 计算结构：字段 close；算子 shift；窗口 shift=28；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=28；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE28。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3421、3427
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close29**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=29。
- 计算结构：字段 close；算子 shift；窗口 shift=29；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=29；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE29。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3431、3437
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=30。
- 计算结构：字段 close；算子 shift；窗口 shift=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=30；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3441、3447
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close31**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=31。
- 计算结构：字段 close；算子 shift；窗口 shift=31；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=31；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE31。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3451、3457
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close32**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=32。
- 计算结构：字段 close；算子 shift；窗口 shift=32；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=32；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE32。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3461、3467
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close33**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=33。
- 计算结构：字段 close；算子 shift；窗口 shift=33；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=33；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE33。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3471、3477
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close34**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=34。
- 计算结构：字段 close；算子 shift；窗口 shift=34；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=34；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE34。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3481、3487
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close35**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=35。
- 计算结构：字段 close；算子 shift；窗口 shift=35；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=35；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE35。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3491、3497
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close36**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=36。
- 计算结构：字段 close；算子 shift；窗口 shift=36；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=36；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE36。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3501、3507
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close37**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=37。
- 计算结构：字段 close；算子 shift；窗口 shift=37；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=37；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE37。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3511、3517
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close38**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=38。
- 计算结构：字段 close；算子 shift；窗口 shift=38；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=38；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE38。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3521、3527
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close39**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=39。
- 计算结构：字段 close；算子 shift；窗口 shift=39；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=39；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE39。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3531、3537
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close40**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=40。
- 计算结构：字段 close；算子 shift；窗口 shift=40；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=40；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE40。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3541、3547
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close41**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=41。
- 计算结构：字段 close；算子 shift；窗口 shift=41；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=41；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE41。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3551、3557
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close42**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=42。
- 计算结构：字段 close；算子 shift；窗口 shift=42；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=42；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE42。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3561、3567
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close43**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=43。
- 计算结构：字段 close；算子 shift；窗口 shift=43；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=43；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE43。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3571、3577
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close44**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=44。
- 计算结构：字段 close；算子 shift；窗口 shift=44；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=44；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE44。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3581、3587
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close45**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=45。
- 计算结构：字段 close；算子 shift；窗口 shift=45；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=45；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE45。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3591、3597
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close46**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=46。
- 计算结构：字段 close；算子 shift；窗口 shift=46；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=46；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE46。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3601、3607
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close47**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=47。
- 计算结构：字段 close；算子 shift；窗口 shift=47；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=47；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE47。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3611、3617
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close48**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=48。
- 计算结构：字段 close；算子 shift；窗口 shift=48；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=48；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE48。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3621、3627
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close49**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=49。
- 计算结构：字段 close；算子 shift；窗口 shift=49；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=49；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE49。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3631、3637
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close50**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=50。
- 计算结构：字段 close；算子 shift；窗口 shift=50；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=50；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE50。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3641、3647
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close51**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=51。
- 计算结构：字段 close；算子 shift；窗口 shift=51；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=51；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE51。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3651、3657
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close52**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=52。
- 计算结构：字段 close；算子 shift；窗口 shift=52；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=52；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE52。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3661、3667
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close53**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=53。
- 计算结构：字段 close；算子 shift；窗口 shift=53；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=53；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE53。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3671、3677
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close54**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=54。
- 计算结构：字段 close；算子 shift；窗口 shift=54；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=54；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE54。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3681、3687
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close55**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=55。
- 计算结构：字段 close；算子 shift；窗口 shift=55；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=55；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE55。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3691、3697
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close56**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=56。
- 计算结构：字段 close；算子 shift；窗口 shift=56；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=56；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE56。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3701、3707
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close57**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=57。
- 计算结构：字段 close；算子 shift；窗口 shift=57；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=57；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE57。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3711、3717
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close58**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=58。
- 计算结构：字段 close；算子 shift；窗口 shift=58；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=58；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE58。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3721、3727
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_close59**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 CLOSE 公式族”；本因子参数为 day=59。
- 计算结构：字段 close；算子 shift；窗口 shift=59；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=59；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 CLOSE59。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3731、3737
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha360 HIGH 公式族（59 个参数变体）

这组因子的共同公式是 `high.shift({day}) / close`。共同输入字段为 high、close，主要算子为 shift；参数梯度为 day ∈ {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59}。

族级解读：day 只改变回看距离，字段决定比较的是价格还是成交量；它们不是彼此独立的 360 种经济逻辑。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha360_high1、alpha360_high2、alpha360_high3 … alpha360_high57、alpha360_high58、alpha360_high59（共 59 个）。

**因子：alpha360_high1**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=1。
- 计算结构：字段 high、close；算子 shift；窗口 shift=1；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=1；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH1。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4351、4357
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high2**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=2。
- 计算结构：字段 high、close；算子 shift；窗口 shift=2；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=2；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH2。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4361、4367
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high3**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=3。
- 计算结构：字段 high、close；算子 shift；窗口 shift=3；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=3；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH3。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4371、4377
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high4**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=4。
- 计算结构：字段 high、close；算子 shift；窗口 shift=4；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=4；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH4。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4381、4387
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=5。
- 计算结构：字段 high、close；算子 shift；窗口 shift=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=5；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4391、4397
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high6**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=6。
- 计算结构：字段 high、close；算子 shift；窗口 shift=6；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=6；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH6。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4401、4407
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high7**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=7。
- 计算结构：字段 high、close；算子 shift；窗口 shift=7；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=7；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH7。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4411、4417
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high8**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=8。
- 计算结构：字段 high、close；算子 shift；窗口 shift=8；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=8；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH8。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4421、4427
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high9**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=9。
- 计算结构：字段 high、close；算子 shift；窗口 shift=9；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=9；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH9。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4431、4437
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=10。
- 计算结构：字段 high、close；算子 shift；窗口 shift=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=10；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4441、4447
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high11**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=11。
- 计算结构：字段 high、close；算子 shift；窗口 shift=11；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=11；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH11。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4451、4457
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high12**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=12。
- 计算结构：字段 high、close；算子 shift；窗口 shift=12；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=12；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH12。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4461、4467
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high13**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=13。
- 计算结构：字段 high、close；算子 shift；窗口 shift=13；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=13；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH13。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4471、4477
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high14**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=14。
- 计算结构：字段 high、close；算子 shift；窗口 shift=14；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=14；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH14。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4481、4487
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high15**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=15。
- 计算结构：字段 high、close；算子 shift；窗口 shift=15；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=15；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH15。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4491、4497
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high16**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=16。
- 计算结构：字段 high、close；算子 shift；窗口 shift=16；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=16；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH16。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4501、4507
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high17**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=17。
- 计算结构：字段 high、close；算子 shift；窗口 shift=17；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=17；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH17。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4511、4517
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high18**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=18。
- 计算结构：字段 high、close；算子 shift；窗口 shift=18；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=18；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH18。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4521、4527
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high19**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=19。
- 计算结构：字段 high、close；算子 shift；窗口 shift=19；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=19；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH19。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4531、4537
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=20。
- 计算结构：字段 high、close；算子 shift；窗口 shift=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=20；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4541、4547
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high21**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=21。
- 计算结构：字段 high、close；算子 shift；窗口 shift=21；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=21；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH21。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4551、4557
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high22**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=22。
- 计算结构：字段 high、close；算子 shift；窗口 shift=22；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=22；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH22。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4561、4567
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high23**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=23。
- 计算结构：字段 high、close；算子 shift；窗口 shift=23；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=23；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH23。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4571、4577
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high24**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=24。
- 计算结构：字段 high、close；算子 shift；窗口 shift=24；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=24；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH24。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4581、4587
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high25**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=25。
- 计算结构：字段 high、close；算子 shift；窗口 shift=25；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=25；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH25。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4591、4597
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high26**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=26。
- 计算结构：字段 high、close；算子 shift；窗口 shift=26；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=26；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH26。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4601、4607
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high27**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=27。
- 计算结构：字段 high、close；算子 shift；窗口 shift=27；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=27；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH27。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4611、4617
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high28**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=28。
- 计算结构：字段 high、close；算子 shift；窗口 shift=28；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=28；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH28。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4621、4627
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high29**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=29。
- 计算结构：字段 high、close；算子 shift；窗口 shift=29；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=29；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH29。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4631、4637
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=30。
- 计算结构：字段 high、close；算子 shift；窗口 shift=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=30；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4641、4647
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high31**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=31。
- 计算结构：字段 high、close；算子 shift；窗口 shift=31；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=31；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH31。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4651、4657
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high32**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=32。
- 计算结构：字段 high、close；算子 shift；窗口 shift=32；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=32；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH32。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4661、4667
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high33**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=33。
- 计算结构：字段 high、close；算子 shift；窗口 shift=33；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=33；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH33。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4671、4677
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high34**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=34。
- 计算结构：字段 high、close；算子 shift；窗口 shift=34；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=34；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH34。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4681、4687
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high35**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=35。
- 计算结构：字段 high、close；算子 shift；窗口 shift=35；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=35；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH35。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4691、4697
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high36**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=36。
- 计算结构：字段 high、close；算子 shift；窗口 shift=36；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=36；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH36。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4701、4707
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high37**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=37。
- 计算结构：字段 high、close；算子 shift；窗口 shift=37；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=37；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH37。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4711、4717
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high38**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=38。
- 计算结构：字段 high、close；算子 shift；窗口 shift=38；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=38；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH38。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4721、4727
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high39**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=39。
- 计算结构：字段 high、close；算子 shift；窗口 shift=39；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=39；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH39。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4731、4737
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high40**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=40。
- 计算结构：字段 high、close；算子 shift；窗口 shift=40；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=40；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH40。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4741、4747
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high41**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=41。
- 计算结构：字段 high、close；算子 shift；窗口 shift=41；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=41；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH41。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4751、4757
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high42**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=42。
- 计算结构：字段 high、close；算子 shift；窗口 shift=42；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=42；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH42。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4761、4767
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high43**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=43。
- 计算结构：字段 high、close；算子 shift；窗口 shift=43；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=43；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH43。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4771、4777
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high44**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=44。
- 计算结构：字段 high、close；算子 shift；窗口 shift=44；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=44；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH44。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4781、4787
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high45**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=45。
- 计算结构：字段 high、close；算子 shift；窗口 shift=45；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=45；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH45。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4791、4797
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high46**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=46。
- 计算结构：字段 high、close；算子 shift；窗口 shift=46；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=46；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH46。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4801、4807
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high47**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=47。
- 计算结构：字段 high、close；算子 shift；窗口 shift=47；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=47；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH47。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4811、4817
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high48**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=48。
- 计算结构：字段 high、close；算子 shift；窗口 shift=48；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=48；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH48。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4821、4827
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high49**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=49。
- 计算结构：字段 high、close；算子 shift；窗口 shift=49；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=49；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH49。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4831、4837
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high50**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=50。
- 计算结构：字段 high、close；算子 shift；窗口 shift=50；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=50；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH50。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4841、4847
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high51**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=51。
- 计算结构：字段 high、close；算子 shift；窗口 shift=51；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=51；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH51。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4851、4857
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high52**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=52。
- 计算结构：字段 high、close；算子 shift；窗口 shift=52；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=52；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH52。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4861、4867
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high53**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=53。
- 计算结构：字段 high、close；算子 shift；窗口 shift=53；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=53；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH53。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4871、4877
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high54**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=54。
- 计算结构：字段 high、close；算子 shift；窗口 shift=54；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=54；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH54。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4881、4887
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high55**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=55。
- 计算结构：字段 high、close；算子 shift；窗口 shift=55；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=55；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH55。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4891、4897
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high56**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=56。
- 计算结构：字段 high、close；算子 shift；窗口 shift=56；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=56；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH56。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4901、4907
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high57**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=57。
- 计算结构：字段 high、close；算子 shift；窗口 shift=57；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=57；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH57。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4911、4917
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high58**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=58。
- 计算结构：字段 high、close；算子 shift；窗口 shift=58；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=58；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH58。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4921、4927
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_high59**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 HIGH 公式族”；本因子参数为 day=59。
- 计算结构：字段 high、close；算子 shift；窗口 shift=59；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=59；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 high、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 HIGH59。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4931、4937
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha360 LOW 公式族（59 个参数变体）

这组因子的共同公式是 `low.shift({day}) / close`。共同输入字段为 low、close，主要算子为 shift；参数梯度为 day ∈ {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59}。

族级解读：day 只改变回看距离，字段决定比较的是价格还是成交量；它们不是彼此独立的 360 种经济逻辑。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha360_low1、alpha360_low2、alpha360_low3 … alpha360_low57、alpha360_low58、alpha360_low59（共 59 个）。

**因子：alpha360_low1**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=1。
- 计算结构：字段 low、close；算子 shift；窗口 shift=1；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=1；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW1。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4951、4957
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low2**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=2。
- 计算结构：字段 low、close；算子 shift；窗口 shift=2；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=2；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW2。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4961、4967
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low3**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=3。
- 计算结构：字段 low、close；算子 shift；窗口 shift=3；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=3；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW3。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4971、4977
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low4**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=4。
- 计算结构：字段 low、close；算子 shift；窗口 shift=4；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=4；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW4。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4981、4987
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=5。
- 计算结构：字段 low、close；算子 shift；窗口 shift=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=5；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4991、4997
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low6**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=6。
- 计算结构：字段 low、close；算子 shift；窗口 shift=6；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=6；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW6。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5001、5007
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low7**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=7。
- 计算结构：字段 low、close；算子 shift；窗口 shift=7；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=7；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW7。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5011、5017
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low8**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=8。
- 计算结构：字段 low、close；算子 shift；窗口 shift=8；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=8；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW8。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5021、5027
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low9**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=9。
- 计算结构：字段 low、close；算子 shift；窗口 shift=9；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=9；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW9。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5031、5037
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=10。
- 计算结构：字段 low、close；算子 shift；窗口 shift=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=10；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5041、5047
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low11**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=11。
- 计算结构：字段 low、close；算子 shift；窗口 shift=11；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=11；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW11。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5051、5057
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low12**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=12。
- 计算结构：字段 low、close；算子 shift；窗口 shift=12；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=12；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW12。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5061、5067
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low13**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=13。
- 计算结构：字段 low、close；算子 shift；窗口 shift=13；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=13；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW13。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5071、5077
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low14**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=14。
- 计算结构：字段 low、close；算子 shift；窗口 shift=14；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=14；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW14。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5081、5087
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low15**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=15。
- 计算结构：字段 low、close；算子 shift；窗口 shift=15；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=15；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW15。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5091、5097
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low16**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=16。
- 计算结构：字段 low、close；算子 shift；窗口 shift=16；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=16；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW16。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5101、5107
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low17**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=17。
- 计算结构：字段 low、close；算子 shift；窗口 shift=17；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=17；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW17。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5111、5117
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low18**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=18。
- 计算结构：字段 low、close；算子 shift；窗口 shift=18；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=18；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW18。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5121、5127
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low19**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=19。
- 计算结构：字段 low、close；算子 shift；窗口 shift=19；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=19；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW19。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5131、5137
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=20。
- 计算结构：字段 low、close；算子 shift；窗口 shift=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=20；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5141、5147
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low21**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=21。
- 计算结构：字段 low、close；算子 shift；窗口 shift=21；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=21；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW21。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5151、5157
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low22**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=22。
- 计算结构：字段 low、close；算子 shift；窗口 shift=22；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=22；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW22。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5161、5167
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low23**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=23。
- 计算结构：字段 low、close；算子 shift；窗口 shift=23；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=23；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW23。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5171、5177
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low24**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=24。
- 计算结构：字段 low、close；算子 shift；窗口 shift=24；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=24；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW24。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5181、5187
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low25**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=25。
- 计算结构：字段 low、close；算子 shift；窗口 shift=25；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=25；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW25。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5191、5197
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low26**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=26。
- 计算结构：字段 low、close；算子 shift；窗口 shift=26；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=26；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW26。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5201、5207
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low27**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=27。
- 计算结构：字段 low、close；算子 shift；窗口 shift=27；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=27；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW27。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5211、5217
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low28**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=28。
- 计算结构：字段 low、close；算子 shift；窗口 shift=28；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=28；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW28。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5221、5227
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low29**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=29。
- 计算结构：字段 low、close；算子 shift；窗口 shift=29；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=29；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW29。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5231、5237
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=30。
- 计算结构：字段 low、close；算子 shift；窗口 shift=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=30；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5241、5247
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low31**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=31。
- 计算结构：字段 low、close；算子 shift；窗口 shift=31；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=31；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW31。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5251、5257
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low32**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=32。
- 计算结构：字段 low、close；算子 shift；窗口 shift=32；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=32；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW32。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5261、5267
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low33**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=33。
- 计算结构：字段 low、close；算子 shift；窗口 shift=33；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=33；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW33。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5271、5277
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low34**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=34。
- 计算结构：字段 low、close；算子 shift；窗口 shift=34；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=34；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW34。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5281、5287
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low35**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=35。
- 计算结构：字段 low、close；算子 shift；窗口 shift=35；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=35；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW35。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5291、5297
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low36**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=36。
- 计算结构：字段 low、close；算子 shift；窗口 shift=36；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=36；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW36。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5301、5307
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low37**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=37。
- 计算结构：字段 low、close；算子 shift；窗口 shift=37；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=37；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW37。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5311、5317
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low38**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=38。
- 计算结构：字段 low、close；算子 shift；窗口 shift=38；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=38；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW38。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5321、5327
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low39**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=39。
- 计算结构：字段 low、close；算子 shift；窗口 shift=39；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=39；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW39。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5331、5337
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low40**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=40。
- 计算结构：字段 low、close；算子 shift；窗口 shift=40；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=40；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW40。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5341、5347
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low41**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=41。
- 计算结构：字段 low、close；算子 shift；窗口 shift=41；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=41；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW41。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5351、5357
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low42**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=42。
- 计算结构：字段 low、close；算子 shift；窗口 shift=42；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=42；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW42。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5361、5367
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low43**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=43。
- 计算结构：字段 low、close；算子 shift；窗口 shift=43；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=43；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW43。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5371、5377
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low44**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=44。
- 计算结构：字段 low、close；算子 shift；窗口 shift=44；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=44；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW44。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5381、5387
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low45**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=45。
- 计算结构：字段 low、close；算子 shift；窗口 shift=45；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=45；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW45。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5391、5397
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low46**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=46。
- 计算结构：字段 low、close；算子 shift；窗口 shift=46；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=46；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW46。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5401、5407
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low47**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=47。
- 计算结构：字段 low、close；算子 shift；窗口 shift=47；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=47；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW47。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5411、5417
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low48**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=48。
- 计算结构：字段 low、close；算子 shift；窗口 shift=48；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=48；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW48。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5421、5427
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low49**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=49。
- 计算结构：字段 low、close；算子 shift；窗口 shift=49；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=49；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW49。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5431、5437
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low50**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=50。
- 计算结构：字段 low、close；算子 shift；窗口 shift=50；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=50；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW50。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5441、5447
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low51**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=51。
- 计算结构：字段 low、close；算子 shift；窗口 shift=51；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=51；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW51。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5451、5457
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low52**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=52。
- 计算结构：字段 low、close；算子 shift；窗口 shift=52；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=52；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW52。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5461、5467
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low53**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=53。
- 计算结构：字段 low、close；算子 shift；窗口 shift=53；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=53；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW53。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5471、5477
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low54**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=54。
- 计算结构：字段 low、close；算子 shift；窗口 shift=54；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=54；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW54。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5481、5487
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low55**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=55。
- 计算结构：字段 low、close；算子 shift；窗口 shift=55；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=55；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW55。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5491、5497
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low56**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=56。
- 计算结构：字段 low、close；算子 shift；窗口 shift=56；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=56；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW56。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5501、5507
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low57**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=57。
- 计算结构：字段 low、close；算子 shift；窗口 shift=57；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=57；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW57。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5511、5517
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low58**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=58。
- 计算结构：字段 low、close；算子 shift；窗口 shift=58；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=58；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW58。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5521、5527
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_low59**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 LOW 公式族”；本因子参数为 day=59。
- 计算结构：字段 low、close；算子 shift；窗口 shift=59；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=59；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 low、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 LOW59。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5531、5537
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha360 OPEN 公式族（59 个参数变体）

这组因子的共同公式是 `open.shift({day}) / close`。共同输入字段为 open、close，主要算子为 shift；参数梯度为 day ∈ {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59}。

族级解读：day 只改变回看距离，字段决定比较的是价格还是成交量；它们不是彼此独立的 360 种经济逻辑。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha360_open1、alpha360_open2、alpha360_open3 … alpha360_open57、alpha360_open58、alpha360_open59（共 59 个）。

**因子：alpha360_open1**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=1。
- 计算结构：字段 open、close；算子 shift；窗口 shift=1；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=1；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN1。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3751、3757
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open2**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=2。
- 计算结构：字段 open、close；算子 shift；窗口 shift=2；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=2；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN2。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3761、3767
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open3**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=3。
- 计算结构：字段 open、close；算子 shift；窗口 shift=3；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=3；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN3。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3771、3777
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open4**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=4。
- 计算结构：字段 open、close；算子 shift；窗口 shift=4；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=4；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN4。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3781、3787
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=5。
- 计算结构：字段 open、close；算子 shift；窗口 shift=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=5；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3791、3797
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open6**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=6。
- 计算结构：字段 open、close；算子 shift；窗口 shift=6；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=6；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN6。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3801、3807
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open7**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=7。
- 计算结构：字段 open、close；算子 shift；窗口 shift=7；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=7；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN7。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3811、3817
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open8**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=8。
- 计算结构：字段 open、close；算子 shift；窗口 shift=8；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=8；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN8。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3821、3827
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open9**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=9。
- 计算结构：字段 open、close；算子 shift；窗口 shift=9；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=9；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN9。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3831、3837
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=10。
- 计算结构：字段 open、close；算子 shift；窗口 shift=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=10；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3841、3847
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open11**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=11。
- 计算结构：字段 open、close；算子 shift；窗口 shift=11；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=11；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN11。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3851、3857
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open12**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=12。
- 计算结构：字段 open、close；算子 shift；窗口 shift=12；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=12；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN12。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3861、3867
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open13**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=13。
- 计算结构：字段 open、close；算子 shift；窗口 shift=13；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=13；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN13。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3871、3877
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open14**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=14。
- 计算结构：字段 open、close；算子 shift；窗口 shift=14；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=14；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN14。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3881、3887
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open15**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=15。
- 计算结构：字段 open、close；算子 shift；窗口 shift=15；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=15；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN15。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3891、3897
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open16**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=16。
- 计算结构：字段 open、close；算子 shift；窗口 shift=16；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=16；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN16。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3901、3907
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open17**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=17。
- 计算结构：字段 open、close；算子 shift；窗口 shift=17；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=17；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN17。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3911、3917
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open18**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=18。
- 计算结构：字段 open、close；算子 shift；窗口 shift=18；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=18；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN18。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3921、3927
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open19**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=19。
- 计算结构：字段 open、close；算子 shift；窗口 shift=19；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=19；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN19。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3931、3937
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=20。
- 计算结构：字段 open、close；算子 shift；窗口 shift=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=20；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3941、3947
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open21**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=21。
- 计算结构：字段 open、close；算子 shift；窗口 shift=21；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=21；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN21。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3951、3957
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open22**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=22。
- 计算结构：字段 open、close；算子 shift；窗口 shift=22；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=22；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN22。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3961、3967
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open23**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=23。
- 计算结构：字段 open、close；算子 shift；窗口 shift=23；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=23；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN23。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3971、3977
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open24**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=24。
- 计算结构：字段 open、close；算子 shift；窗口 shift=24；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=24；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN24。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3981、3987
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open25**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=25。
- 计算结构：字段 open、close；算子 shift；窗口 shift=25；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=25；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN25。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3991、3997
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open26**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=26。
- 计算结构：字段 open、close；算子 shift；窗口 shift=26；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=26；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN26。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4001、4007
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open27**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=27。
- 计算结构：字段 open、close；算子 shift；窗口 shift=27；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=27；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN27。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4011、4017
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open28**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=28。
- 计算结构：字段 open、close；算子 shift；窗口 shift=28；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=28；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN28。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4021、4027
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open29**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=29。
- 计算结构：字段 open、close；算子 shift；窗口 shift=29；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=29；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN29。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4031、4037
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=30。
- 计算结构：字段 open、close；算子 shift；窗口 shift=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=30；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4041、4047
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open31**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=31。
- 计算结构：字段 open、close；算子 shift；窗口 shift=31；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=31；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN31。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4051、4057
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open32**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=32。
- 计算结构：字段 open、close；算子 shift；窗口 shift=32；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=32；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN32。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4061、4067
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open33**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=33。
- 计算结构：字段 open、close；算子 shift；窗口 shift=33；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=33；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN33。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4071、4077
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open34**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=34。
- 计算结构：字段 open、close；算子 shift；窗口 shift=34；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=34；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN34。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4081、4087
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open35**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=35。
- 计算结构：字段 open、close；算子 shift；窗口 shift=35；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=35；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN35。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4091、4097
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open36**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=36。
- 计算结构：字段 open、close；算子 shift；窗口 shift=36；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=36；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN36。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4101、4107
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open37**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=37。
- 计算结构：字段 open、close；算子 shift；窗口 shift=37；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=37；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN37。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4111、4117
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open38**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=38。
- 计算结构：字段 open、close；算子 shift；窗口 shift=38；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=38；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN38。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4121、4127
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open39**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=39。
- 计算结构：字段 open、close；算子 shift；窗口 shift=39；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=39；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN39。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4131、4137
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open40**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=40。
- 计算结构：字段 open、close；算子 shift；窗口 shift=40；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=40；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN40。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4141、4147
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open41**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=41。
- 计算结构：字段 open、close；算子 shift；窗口 shift=41；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=41；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN41。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4151、4157
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open42**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=42。
- 计算结构：字段 open、close；算子 shift；窗口 shift=42；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=42；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN42。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4161、4167
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open43**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=43。
- 计算结构：字段 open、close；算子 shift；窗口 shift=43；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=43；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN43。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4171、4177
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open44**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=44。
- 计算结构：字段 open、close；算子 shift；窗口 shift=44；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=44；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN44。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4181、4187
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open45**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=45。
- 计算结构：字段 open、close；算子 shift；窗口 shift=45；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=45；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN45。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4191、4197
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open46**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=46。
- 计算结构：字段 open、close；算子 shift；窗口 shift=46；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=46；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN46。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4201、4207
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open47**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=47。
- 计算结构：字段 open、close；算子 shift；窗口 shift=47；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=47；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN47。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4211、4217
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open48**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=48。
- 计算结构：字段 open、close；算子 shift；窗口 shift=48；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=48；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN48。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4221、4227
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open49**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=49。
- 计算结构：字段 open、close；算子 shift；窗口 shift=49；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=49；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN49。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4231、4237
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open50**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=50。
- 计算结构：字段 open、close；算子 shift；窗口 shift=50；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=50；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN50。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4241、4247
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open51**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=51。
- 计算结构：字段 open、close；算子 shift；窗口 shift=51；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=51；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN51。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4251、4257
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open52**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=52。
- 计算结构：字段 open、close；算子 shift；窗口 shift=52；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=52；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN52。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4261、4267
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open53**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=53。
- 计算结构：字段 open、close；算子 shift；窗口 shift=53；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=53；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN53。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4271、4277
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open54**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=54。
- 计算结构：字段 open、close；算子 shift；窗口 shift=54；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=54；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN54。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4281、4287
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open55**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=55。
- 计算结构：字段 open、close；算子 shift；窗口 shift=55；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=55；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN55。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4291、4297
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open56**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=56。
- 计算结构：字段 open、close；算子 shift；窗口 shift=56；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=56；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN56。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4301、4307
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open57**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=57。
- 计算结构：字段 open、close；算子 shift；窗口 shift=57；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=57；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN57。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4311、4317
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open58**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=58。
- 计算结构：字段 open、close；算子 shift；窗口 shift=58；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=58；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN58。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4321、4327
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_open59**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 OPEN 公式族”；本因子参数为 day=59。
- 计算结构：字段 open、close；算子 shift；窗口 shift=59；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=59；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 open、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 OPEN59。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4331、4337
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha360 VWAP 公式族（59 个参数变体）

这组因子的共同公式是 `vwap.shift({day}) / close`。共同输入字段为 vwap、close，主要算子为 shift、vwap；参数梯度为 day ∈ {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59}。

族级解读：day 只改变回看距离，字段决定比较的是价格还是成交量；它们不是彼此独立的 360 种经济逻辑。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha360_vwap1、alpha360_vwap2、alpha360_vwap3 … alpha360_vwap57、alpha360_vwap58、alpha360_vwap59（共 59 个）。

**因子：alpha360_vwap1**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=1。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=1；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=1；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP1。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5551、5557
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap2**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=2。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=2；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=2；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP2。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5561、5567
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap3**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=3。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=3；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=3；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP3。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5571、5577
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap4**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=4。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=4；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=4；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP4。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5581、5587
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap5**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=5。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=5；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5591、5597
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap6**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=6。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=6；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=6；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP6。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5601、5607
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap7**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=7。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=7；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=7；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP7。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5611、5617
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap8**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=8。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=8；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=8；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP8。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5621、5627
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap9**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=9。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=9；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=9；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP9。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5631、5637
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap10**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=10。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=10；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5641、5647
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap11**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=11。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=11；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=11；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP11。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5651、5657
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap12**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=12。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=12；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=12；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP12。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5661、5667
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap13**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=13。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=13；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=13；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP13。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5671、5677
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap14**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=14。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=14；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=14；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP14。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5681、5687
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap15**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=15。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=15；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=15；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP15。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5691、5697
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap16**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=16。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=16；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=16；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP16。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5701、5707
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap17**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=17。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=17；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=17；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP17。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5711、5717
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap18**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=18。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=18；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=18；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP18。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5721、5727
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap19**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=19。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=19；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=19；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP19。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5731、5737
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap20**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=20。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=20；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5741、5747
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap21**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=21。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=21；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=21；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP21。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5751、5757
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap22**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=22。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=22；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=22；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP22。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5761、5767
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap23**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=23。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=23；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=23；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP23。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5771、5777
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap24**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=24。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=24；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=24；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP24。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5781、5787
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap25**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=25。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=25；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=25；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP25。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5791、5797
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap26**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=26。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=26；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=26；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP26。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5801、5807
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap27**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=27。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=27；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=27；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP27。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5811、5817
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap28**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=28。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=28；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=28；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP28。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5821、5827
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap29**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=29。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=29；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=29；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP29。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5831、5837
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap30**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=30。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=30；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5841、5847
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap31**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=31。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=31；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=31；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP31。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5851、5857
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap32**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=32。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=32；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=32；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP32。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5861、5867
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap33**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=33。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=33；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=33；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP33。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5871、5877
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap34**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=34。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=34；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=34；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP34。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5881、5887
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap35**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=35。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=35；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=35；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP35。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5891、5897
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap36**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=36。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=36；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=36；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP36。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5901、5907
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap37**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=37。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=37；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=37；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP37。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5911、5917
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap38**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=38。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=38；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=38；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP38。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5921、5927
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap39**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=39。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=39；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=39；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP39。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5931、5937
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap40**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=40。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=40；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=40；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP40。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5941、5947
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap41**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=41。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=41；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=41；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP41。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5951、5957
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap42**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=42。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=42；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=42；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP42。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5961、5967
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap43**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=43。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=43；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=43；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP43。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5971、5977
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap44**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=44。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=44；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=44；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP44。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5981、5987
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap45**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=45。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=45；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=45；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP45。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5991、5997
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap46**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=46。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=46；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=46；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP46。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6001、6007
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap47**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=47。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=47；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=47；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP47。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6011、6017
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap48**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=48。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=48；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=48；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP48。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6021、6027
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap49**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=49。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=49；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=49；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP49。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6031、6037
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap50**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=50。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=50；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=50；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP50。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6041、6047
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap51**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=51。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=51；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=51；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP51。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6051、6057
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap52**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=52。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=52；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=52；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP52。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6061、6067
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap53**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=53。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=53；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=53；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP53。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6071、6077
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap54**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=54。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=54；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=54；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP54。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6081、6087
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap55**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=55。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=55；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=55；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP55。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6091、6097
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap56**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=56。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=56；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=56；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP56。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6101、6107
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap57**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=57。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=57；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=57；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP57。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6111、6117
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap58**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=58。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=58；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=58；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP58。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6121、6127
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_vwap59**
- 主分类：动量与反转
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 本条参数差异：沿用上述“Alpha360 VWAP 公式族”；本因子参数为 day=59。
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=59；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=59；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 vwap、close；含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VWAP59。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6131、6137
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha101
- 主分类：动量与反转
- 因子库来源：alpha_library（历史兼容示例，需区分研究特征与标签）
- 辅助标签：close、收益变化
- 计算结构：字段 close；算子 pct_change；窗口 window=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：动量因子：过去 ``window`` 日收益率。
- 源码计算片段："""动量因子：过去 ``window`` 日收益率。""" return self.close.pct_change(window)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的收益变化实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；收益变化 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：动量因子：过去 ``window`` 日收益率。
- 来源证据：Factor/libraries/alpha_library.py / alpha101 / 第 19-21 行；总览匹配行 6、54、56
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### alpha158
- 主分类：动量与反转
- 因子库来源：alpha_library（历史兼容示例，需区分研究特征与标签）
- 辅助标签：close、收益变化
- 计算结构：字段 close；算子 pct_change；窗口 window=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：反转因子：-过去 ``window`` 日收益率。
- 源码计算片段："""反转因子：-过去 ``window`` 日收益率。""" return -self.close.pct_change(window)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的收益变化实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；收益变化 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：反转因子：-过去 ``window`` 日收益率。
- 来源证据：Factor/libraries/alpha_library.py / alpha158 / 第 23-25 行；总览匹配行 93、101
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### macdboll
- 主分类：动量与反转
- 因子库来源：alpha_library（历史兼容示例，需区分研究特征与标签）
- 辅助标签：close、ewm、均值、滚动窗口、标准差
- 计算结构：字段 close；算子 ewm、mean、rolling、std；窗口 rolling=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：macdboll
- 源码计算片段：ema12 = self.close.ewm(span=12).mean() ema26 = self.close.ewm(span=26).mean() dif = ema12 - ema26 dea = dif.ewm(span=9).mean() macd = dif - dea mid = self.close.rolling(20).mean() std = self.close.rolling(20).std() upper = mid + 2 * std lower = mid - 2 * std boll_pos = (self.close - lower) / (upper - lower) return macd * (1 - boll_pos)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的ewm、均值、滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；ewm、均值、滚动窗口、标准差 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：macdboll
- 来源证据：Factor/libraries/alpha_library.py / macdboll / 第 30-45 行；总览匹配行 118、126
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### macd
- 主分类：动量与反转
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、ewm、均值
- 计算结构：字段 close；算子 ewm、mean；窗口 fast=12、slow=26；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：MACD 柱值 BAR：2 * (DIF - DEA)。
- 源码计算片段："""MACD 柱值 BAR：2 * (DIF - DEA)。""" diff = self.close.ewm(span=fast, adjust=False).mean() - self.close.ewm(span=slow, adjust=False).mean() dea = diff.ewm(span=signal, adjust=False).mean() return 2 * (diff - dea)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；ewm、均值 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：MACD 柱值 BAR：2 * (DIF - DEA)。
- 来源证据：Factor/libraries/classic_indicators.py / macd / 第 61-65 行；总览匹配行 131、141、629
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### roc
- 主分类：动量与反转
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、收益变化
- 计算结构：字段 close；算子 pct_change；窗口 window=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：变动速率。
- 源码计算片段："""变动速率。""" return self.close.pct_change(window) * 100
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的收益变化实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；收益变化 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：变动速率。
- 来源证据：Factor/libraries/classic_indicators.py / roc / 第 119-121 行；总览匹配行 638
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### rsi
- 主分类：动量与反转
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、abs、clip、diff
- 计算结构：字段 close；算子 abs、clip、diff；窗口 window=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：Wilder/通达信式相对强弱指标。
- 源码计算片段："""Wilder/通达信式相对强弱指标。""" change = self.close.diff() numerator = self._sma(change.clip(lower=0), window) denominator = self._sma(change.abs(), window) return numerator / denominator * 100
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的abs、clip、diff实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；abs、clip、diff 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：Wilder/通达信式相对强弱指标。
- 来源证据：Factor/libraries/classic_indicators.py / rsi / 第 123-128 行；总览匹配行 639、930、931
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vmacd
- 主分类：动量与反转
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：volume、ewm、均值
- 计算结构：字段 volume；算子 ewm、mean；窗口 fast=12、slow=26；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：成交量 MACD 柱值。
- 源码计算片段："""成交量 MACD 柱值。""" diff = self.volume.ewm(span=fast, adjust=False).mean() - self.volume.ewm(span=slow, adjust=False).mean() return 2 * (diff - diff.ewm(span=signal, adjust=False).mean())
- 本类中的具体角色：它在“动量与反转”总论中具体通过 volume 的ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 volume 的近期变化、历史位置或极值位置转成强弱信号；ewm、均值 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 volume；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：成交量 MACD 柱值。
- 来源证据：Factor/libraries/classic_indicators.py / vmacd / 第 207-210 行；总览匹配行 646、2936、2944
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vroc
- 主分类：动量与反转
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：volume、收益变化
- 计算结构：字段 volume；算子 pct_change；窗口 window=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：成交量变动速率。
- 源码计算片段："""成交量变动速率。""" return self.volume.pct_change(window) * 100
- 本类中的具体角色：它在“动量与反转”总论中具体通过 volume 的收益变化实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 volume 的近期变化、历史位置或极值位置转成强弱信号；收益变化 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 volume；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：成交量变动速率。
- 来源证据：Factor/libraries/classic_indicators.py / vroc / 第 137-139 行；总览匹配行 649
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### momentum_acceleration
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、收益变化
- 计算结构：字段 close；算子 pct_change；窗口 fast=5、slow=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：动量加速度：短期动量 - 长期动量。
- 源码计算片段："""动量加速度：短期动量 - 长期动量。""" return self.close.pct_change(fast) - self.close.pct_change(slow)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的收益变化实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；收益变化 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：动量加速度：短期动量 - 长期动量。
- 来源证据：Factor/libraries/momentum_lib.py / momentum_acceleration / 第 50-52 行；总览匹配行 253、261
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### momentum_decay
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、apply、收益变化、滚动窗口、求和
- 计算结构：字段 close；算子 apply、pct_change、rolling、sum；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：指数衰减动量：对每日收益率加权平均，越近权重越高。
- 源码计算片段："""指数衰减动量：对每日收益率加权平均，越近权重越高。""" ret = self.close.pct_change() weights = [decay ** i for i in range(window)] weights = weights[::-1] # 最近权重最大 weights = [w / sum(weights) for w in weights] return ret.rolling(window).apply(lambda x: (x * weights).sum(), raw=True)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的apply、收益变化、滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；apply、收益变化、滚动窗口、求和 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：指数衰减动量：对每日收益率加权平均，越近权重越高。
- 来源证据：Factor/libraries/momentum_lib.py / momentum_decay / 第 54-60 行；总览匹配行 266、274
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### momentum_ratio
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、abs、收益变化
- 计算结构：字段 close；算子 abs、pct_change；窗口 short=5、long=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：动量比：短期动量 / 长期动量。
- 源码计算片段："""动量比：短期动量 / 长期动量。""" short_ret = self.close.pct_change(short) long_ret = self.close.pct_change(long).abs() return short_ret / (long_ret + 1e-10)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的abs、收益变化实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；abs、收益变化 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：动量比：短期动量 / 长期动量。
- 来源证据：Factor/libraries/momentum_lib.py / momentum_ratio / 第 44-48 行；总览匹配行 238、246
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### momentum_risk_adjusted
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、收益变化、滚动窗口、标准差
- 计算结构：字段 close；算子 pct_change、rolling、std；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：风险调整动量：收益率 / 波动率。
- 源码计算片段："""风险调整动量：收益率 / 波动率。""" ret = self.close.pct_change(window) vol = self.close.pct_change().rolling(window).std() return ret / (vol + 1e-10)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的收益变化、滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；收益变化、滚动窗口、标准差 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：风险调整动量：收益率 / 波动率。
- 来源证据：Factor/libraries/momentum_lib.py / momentum_risk_adjusted / 第 62-66 行；总览匹配行 283、291
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### reversal_industry_neutral
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、收益变化
- 计算结构：字段 close；算子 pct_change；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：行业中性反转：减去行业均值。
- 源码计算片段："""行业中性反转：减去行业均值。""" raw = -self.close.pct_change(window) # 行业中性化由系统处理，此处直接返回原始值 return raw
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的收益变化实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；收益变化 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：行业中性反转：减去行业均值。
- 来源证据：Factor/libraries/momentum_lib.py / reversal_industry_neutral / 第 86-90 行；总览匹配行 350、358
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### trend_consistency
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、diff、均值、滚动窗口
- 计算结构：字段 close；算子 diff、mean、rolling；窗口 window=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：趋势一致性：上涨天数占比。
- 源码计算片段："""趋势一致性：上涨天数占比。""" up = (self.close.diff() > 0).astype(float) return up.rolling(window).mean()
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的diff、均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；diff、均值、滚动窗口 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：趋势一致性：上涨天数占比。
- 来源证据：Factor/libraries/momentum_lib.py / trend_consistency / 第 104-107 行；总览匹配行 393、401
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### trend_position
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、high、low、滚动最大值、滚动最小值、滚动窗口
- 计算结构：字段 close、high、low；算子 max、min、rolling；窗口 window=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：趋势位置：（当前价 - 最低价）/（最高价 - 最低价）。
- 源码计算片段："""趋势位置：（当前价 - 最低价）/（最高价 - 最低价）。""" hh = self.high.rolling(window).max() ll = self.low.rolling(window).min() return (self.close - ll) / (hh - ll + 1e-10)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close、high、low 的滚动最大值、滚动最小值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、high、low 的近期变化、历史位置或极值位置转成强弱信号；滚动最大值、滚动最小值、滚动窗口 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close、high、low；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：趋势位置：（当前价 - 最低价）/（最高价 - 最低价）。
- 来源证据：Factor/libraries/momentum_lib.py / trend_position / 第 98-102 行；总览匹配行 378、386
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### trend_strength
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：趋势强度：当前价 / 均价。
- 源码计算片段："""趋势强度：当前价 / 均价。""" return self.close / self.close.rolling(window).mean()
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；均值、滚动窗口 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：趋势强度：当前价 / 均价。
- 来源证据：Factor/libraries/momentum_lib.py / trend_strength / 第 94-96 行；总览匹配行 365、373
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### momentum 公式族（6 个参数变体）

这组因子的共同公式是 `self.close.pct_change(window)`。共同输入字段为 close，主要算子为 pct_change；参数梯度为 window ∈ {5, 10, 20, 60, 120, 250}。

族级解读：共同公式把 close 的 window 日收益率作为趋势强度；窗口越短越敏感，越长越平滑，成员之间改变的是观察周期而不是经济对象。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：momentum_5d、momentum_10d、momentum_20d、momentum_60d、momentum_120d、momentum_250d。

**因子：momentum_5d**
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、收益变化
- 本条参数差异：沿用上述“momentum 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 pct_change；窗口 window=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=5；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：5 日动量：过去 window 日收益率。
- 来源证据：Factor/libraries/momentum_lib.py / momentum_5d / 第 18-20 行；总览匹配行 160、168
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：momentum_10d**
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、收益变化
- 本条参数差异：沿用上述“momentum 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 pct_change；窗口 window=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=10；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：10 日动量。
- 来源证据：Factor/libraries/momentum_lib.py / momentum_10d / 第 22-24 行；总览匹配行 173、181
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：momentum_20d**
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、收益变化
- 本条参数差异：沿用上述“momentum 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 pct_change；窗口 window=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=20；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：20 日动量（约月）。
- 来源证据：Factor/libraries/momentum_lib.py / momentum_20d / 第 26-28 行；总览匹配行 186、194
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：momentum_60d**
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、收益变化
- 本条参数差异：沿用上述“momentum 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 pct_change；窗口 window=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=60；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：60 日动量（约季）。
- 来源证据：Factor/libraries/momentum_lib.py / momentum_60d / 第 30-32 行；总览匹配行 199、207
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：momentum_120d**
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、收益变化
- 本条参数差异：沿用上述“momentum 公式族”；本因子参数为 window=120。
- 计算结构：字段 close；算子 pct_change；窗口 window=120；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=120；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：120 日动量（约半年）。
- 来源证据：Factor/libraries/momentum_lib.py / momentum_120d / 第 34-36 行；总览匹配行 212、220
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：momentum_250d**
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、收益变化
- 本条参数差异：沿用上述“momentum 公式族”；本因子参数为 window=250。
- 计算结构：字段 close；算子 pct_change；窗口 window=250；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=250；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：250 日动量（约年）。
- 来源证据：Factor/libraries/momentum_lib.py / momentum_250d / 第 38-40 行；总览匹配行 225、233
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### reversal_1d
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、收益变化
- 计算结构：字段 close；算子 pct_change；窗口 pct_change=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：1 日反转。
- 源码计算片段："""1 日反转。""" return -self.close.pct_change(1)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的收益变化实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；收益变化 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：1 日反转。
- 来源证据：Factor/libraries/momentum_lib.py / reversal_1d / 第 70-72 行；总览匹配行 298、306
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### reversal 公式族（3 个参数变体）

这组因子的共同公式是 `-self.close.pct_change(window)`。共同输入字段为 close，主要算子为 pct_change；参数梯度为 window ∈ {5, 20, 60}。

族级解读：共同公式对 close 的 window 日收益率取反，表达短期价格变化的反向观察；窗口只改变反转观察的时间尺度。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：reversal_5d、reversal_20d、reversal_60d。

**因子：reversal_5d**
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、收益变化
- 本条参数差异：沿用上述“reversal 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 pct_change；窗口 window=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=5；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：5 日反转。
- 来源证据：Factor/libraries/momentum_lib.py / reversal_5d / 第 74-76 行；总览匹配行 311、319
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：reversal_20d**
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、收益变化
- 本条参数差异：沿用上述“reversal 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 pct_change；窗口 window=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=20；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：20 日反转。
- 来源证据：Factor/libraries/momentum_lib.py / reversal_20d / 第 78-80 行；总览匹配行 324、332
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：reversal_60d**
- 主分类：动量与反转
- 因子库来源：momentum_lib（动量、反转与趋势强度）
- 辅助标签：close、收益变化
- 本条参数差异：沿用上述“reversal 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 pct_change；窗口 window=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=60；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：60 日反转。
- 来源证据：Factor/libraries/momentum_lib.py / reversal_60d / 第 82-84 行；总览匹配行 337、345
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### macdc
- 主分类：动量与反转
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、ewm、均值
- 计算结构：字段 close；算子 ewm、mean；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 MACDC：MACD 柱值除以当日收盘价。
- 源码计算片段："""聚宽 MACDC：MACD 柱值除以当日收盘价。""" fast = self.close.ewm(span=12, adjust=False).mean() slow = self.close.ewm(span=26, adjust=False).mean() diff = fast - slow dea = diff.ewm(span=9, adjust=False).mean() return (diff - dea) / self.close
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；ewm、均值 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 MACDC：MACD 柱值除以当日收盘价。
- 来源证据：Factor/libraries/technical_indicators.py / macdc / 第 67-73 行；总览匹配行 2393、2401
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### chande_momentum_oscillator
- 主分类：动量与反转
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、clip、diff、滚动窗口、求和
- 计算结构：字段 close；算子 clip、diff、rolling、sum；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：Chande 动量振荡器：窗口内涨跌价格变动的归一化差。
- 源码计算片段："""Chande 动量振荡器：窗口内涨跌价格变动的归一化差。""" delta = self.close.diff() up_sum = delta.clip(lower=0).rolling(window).sum() down_sum = (-delta.clip(upper=0)).rolling(window).sum() return 100 * (up_sum - down_sum) / (up_sum + down_sum + 1e-10)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的clip、diff、滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；clip、diff、滚动窗口、求和 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：Chande 动量振荡器：窗口内涨跌价格变动的归一化差。
- 来源证据：Factor/libraries/technical_lib.py / chande_momentum_oscillator / 第 182-187 行；总览匹配行 1005、1012
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### macd
- 主分类：动量与反转
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、ewm、均值
- 计算结构：字段 close；算子 ewm、mean；窗口 fast=12、slow=26；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：MACD 因子。
- 源码计算片段："""MACD 因子。""" ema_fast = self.close.ewm(span=fast).mean() ema_slow = self.close.ewm(span=slow).mean() dif = ema_fast - ema_slow dea = dif.ewm(span=signal).mean() return dif - dea
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；ewm、均值 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：MACD 因子。
- 来源证据：Factor/libraries/technical_lib.py / macd / 第 75-81 行；总览匹配行 131、141、629
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### macd_cross
- 主分类：动量与反转
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、apply、ewm、均值、滚动窗口
- 计算结构：字段 close；算子 apply、ewm、mean、rolling；窗口 rolling=2、fast=12、slow=26；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：MACD 金叉死叉信号。
- 源码计算片段："""MACD 金叉死叉信号。""" ema_fast = self.close.ewm(span=fast).mean() ema_slow = self.close.ewm(span=slow).mean() dif = ema_fast - ema_slow dea = dif.ewm(span=signal).mean() hist = dif - dea cross = hist.rolling(2).apply(lambda x: x.iloc[-1] - x.iloc[0], raw=True) return cross
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的apply、ewm、均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；apply、ewm、均值、滚动窗口 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：MACD 金叉死叉信号。
- 来源证据：Factor/libraries/technical_lib.py / macd_cross / 第 91-99 行；总览匹配行 820、828
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### macd_signal
- 主分类：动量与反转
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、abs、ewm、均值
- 计算结构：字段 close；算子 abs、ewm、mean；窗口 fast=12、slow=26；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：MACD 信号线：DIF - DEA 的归一化。
- 源码计算片段："""MACD 信号线：DIF - DEA 的归一化。""" ema_fast = self.close.ewm(span=fast).mean() ema_slow = self.close.ewm(span=slow).mean() dif = ema_fast - ema_slow dea = dif.ewm(span=signal).mean() return (dif - dea) / (dif.abs().mean() + 1e-10)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的abs、ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；abs、ewm、均值 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：MACD 信号线：DIF - DEA 的归一化。
- 来源证据：Factor/libraries/technical_lib.py / macd_signal / 第 83-89 行；总览匹配行 803、811
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### range_expansion_persistence
- 主分类：动量与反转
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：均值、滚动窗口、where
- 计算结构：字段 未从局部源码提取；算子 mean、rolling、where；窗口 window=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：区间扩张持续性：近期真实区间高于基准区间均值的比例。
- 源码计算片段："""区间扩张持续性：近期真实区间高于基准区间均值的比例。""" window = self._validate_window(window) baseline = self._validate_window(baseline) true_range = self._true_range() baseline_range = true_range.rolling(baseline).mean() expanded = true_range.gt(baseline_range).where( true_range.notna() & baseline_range.notna() ) return expanded.astype(float).rolling(window).mean()
- 本类中的具体角色：它在“动量与反转”总论中具体通过 源码局部未识别字段 的均值、滚动窗口、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的近期变化、历史位置或极值位置转成强弱信号；均值、滚动窗口、where 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：区间扩张持续性：近期真实区间高于基准区间均值的比例。
- 来源证据：Factor/libraries/technical_lib.py / range_expansion_persistence / 第 405-414 行；总览匹配行 1389、1398
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### return_autocorrelation
- 主分类：动量与反转
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、clip、均值、收益变化、滚动窗口、历史位移
- 计算结构：字段 close；算子 clip、mean、pct_change、rolling、shift、sqrt、where；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：收益一阶自相关：衡量窗口内收益的延续或反转关系。
- 源码计算片段："""收益一阶自相关：衡量窗口内收益的延续或反转关系。""" window = self._validate_window(window) lag = self._validate_window(lag, minimum=1) if lag >= window: raise ValueError("lag 必须小于 window") returns = self.close.pct_change(fill_method=None).replace( [np.inf, -np.inf], np.nan ) lagged = returns.shift(lag) current_mean = returns.rolling(window).mean() lagged_mean = lagged.rolling(window).mean() covariance = ( (returns * lagged).rolling(window).mean() - current_mean * lagged_mean ) current_variance = ( returns.pow(2).rolling(window).mean()…
- 本类中的具体角色：它在“动量与反转”总论中具体通过 close 的clip、均值、收益变化、滚动窗口、历史位移实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；clip、均值、收益变化、滚动窗口、历史位移、sqrt 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：收益一阶自相关：衡量窗口内收益的延续或反转关系。
- 来源证据：Factor/libraries/technical_lib.py / return_autocorrelation / 第 448-478 行；总览匹配行 1452、1461
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### stoch_rsi
- 主分类：动量与反转
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：滚动最大值、滚动最小值、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 max、min、rolling；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：随机 RSI。
- 源码计算片段："""随机 RSI。""" rsi = self.rsi_14(window=window) hh = rsi.rolling(window).max() ll = rsi.rolling(window).min() return (rsi - ll) / (hh - ll + 1e-10)
- 本类中的具体角色：它在“动量与反转”总论中具体通过 源码局部未识别字段 的滚动最大值、滚动最小值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的近期变化、历史位置或极值位置转成强弱信号；滚动最大值、滚动最小值、滚动窗口 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：随机 RSI。
- 来源证据：Factor/libraries/technical_lib.py / stoch_rsi / 第 141-146 行；总览匹配行 920、928
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### rsi 公式族（3 个参数变体）

这组因子的共同公式是 `delta = self.close.diff() gain = delta.clip(lower=0).rolling(window).mean() loss = -delta.clip(upper=0).rolling(window).mean() rs = gain / (loss + 1e-10) return 100 - 100 / (1 + rs)`。共同输入字段为 close，主要算子为 clip、diff、mean、rolling；参数梯度为 window ∈ {6, 14, 24}。

族级解读：共同公式把上涨和下跌的 window 日平均变化转成相对强弱；窗口改变状态平滑程度和反应速度。 当前分类为“动量与反转”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：rsi_6、rsi_14、rsi_24。

**因子：rsi_6**
- 主分类：动量与反转
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、clip、diff、均值、滚动窗口
- 本条参数差异：沿用上述“rsi 公式族”；本因子参数为 window=6。
- 计算结构：字段 close；算子 clip、diff、mean、rolling；窗口 window=6；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=6；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；滚动窗口前置样本不足时会产生空值。
- 索引说明：6 日 RSI。
- 来源证据：Factor/libraries/technical_lib.py / rsi_6 / 第 49-55 行；总览匹配行 735、743
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：rsi_14**
- 主分类：动量与反转
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、clip、diff、均值、滚动窗口
- 本条参数差异：沿用上述“rsi 公式族”；本因子参数为 window=14。
- 计算结构：字段 close；算子 clip、diff、mean、rolling；窗口 window=14；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=14；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；滚动窗口前置样本不足时会产生空值。
- 索引说明：14 日 RSI。
- 来源证据：Factor/libraries/technical_lib.py / rsi_14 / 第 57-63 行；总览匹配行 752、760、930
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：rsi_24**
- 主分类：动量与反转
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、clip、diff、均值、滚动窗口
- 本条参数差异：沿用上述“rsi 公式族”；本因子参数为 window=24。
- 计算结构：字段 close；算子 clip、diff、mean、rolling；窗口 window=24；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=24；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；滚动窗口前置样本不足时会产生空值。
- 索引说明：24 日 RSI。
- 来源证据：Factor/libraries/technical_lib.py / rsi_24 / 第 65-71 行；总览匹配行 769、777
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### alpha004
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：low、截面排名、时间序列排名、动态生成
- 计算结构：字段 low；算子 rank、ts_rank；窗口 ts_rank=9；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：低位做空信号；核心算子：ts_rank。
- 源码计算片段：return -_ts_rank(_rank(library.low), 9)
- 本类中的具体角色：文章来源把它概括为“低位做空信号”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 low 的近期变化、历史位置或极值位置转成强弱信号；截面排名、时间序列排名 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 low；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #004。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha004 / 第 280-281 行；总览匹配行 8424
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha008
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：open、历史滞后、截面排名、收益序列、滚动求和、动态生成
- 计算结构：字段 open；算子 delay、rank、returns、ts_sum；窗口 ts_sum=5、delay=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：开盘价变化与收益排名的交互；核心算子：rank, delta, sum。
- 源码计算片段：value = _ts_sum(library.open, 5) * _ts_sum(_returns(library), 5) return -_rank(value - _delay(value, 10))
- 本类中的具体角色：文章来源把它概括为“开盘价变化与收益排名的交互”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 open 的近期变化、历史位置或极值位置转成强弱信号；历史滞后、截面排名、收益序列、滚动求和 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 open；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #008。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha008 / 第 301-303 行；总览匹配行 8477
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha009
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、条件分支、窗口差分、滚动最大值、滚动最小值、动态生成
- 计算结构：字段 close；算子 conditional、delta、ts_max、ts_min；窗口 delta=1、ts_min=5、ts_max=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：条件反转：趋势 vs 震荡；核心算子：delta, ts_min/max。
- 源码计算片段：delta = _delta(library.close, 1) return _conditional( _ts_min(delta, 5) > 0, delta, _conditional(_ts_max(delta, 5) < 0, delta, -delta), )
- 本类中的具体角色：文章来源把它概括为“条件反转：趋势 vs 震荡”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；条件分支、窗口差分、滚动最大值、滚动最小值 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #009。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha009 / 第 306-312 行；总览匹配行 8490
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha010
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、条件分支、窗口差分、截面排名、滚动最大值、滚动最小值、动态生成
- 计算结构：字段 close；算子 conditional、delta、rank、ts_max、ts_min；窗口 delta=1、ts_min=4、ts_max=4；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：与 #9 类似的条件动量；核心算子：delta, ts_min/max。
- 源码计算片段：delta = _delta(library.close, 1) value = _conditional( _ts_min(delta, 4) > 0, delta, _conditional(_ts_max(delta, 4) < 0, delta, -delta), ) return _rank(value)
- 本类中的具体角色：文章来源把它概括为“与 #9 类似的条件动量”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；条件分支、窗口差分、截面排名、滚动最大值、滚动最小值 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #010。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha010 / 第 315-322 行；总览匹配行 8352、8507
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha019
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、历史滞后、窗口差分、截面排名、收益序列、sign、动态生成
- 计算结构：字段 close；算子 delay、delta、rank、returns、sign、ts_sum；窗口 delta=7、ts_sum=250、delay=7；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：条件收益率反转；核心算子：returns, delay。
- 源码计算片段：delta = _delta(library.close, 7) return -np.sign((library.close - _delay(library.close, 7)) + delta) * ( 1.0 + _rank(1.0 + _ts_sum(_returns(library), 250)) )
- 本类中的具体角色：文章来源把它概括为“条件收益率反转”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；历史滞后、窗口差分、截面排名、收益序列、sign、滚动求和 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #019。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha019 / 第 375-379 行；总览匹配行 8639
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha020
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、open、历史滞后、截面排名、动态生成
- 计算结构：字段 close、high、low、open；算子 delay、rank；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：跳空缺口回补；核心算子：rank, open, delay。
- 源码计算片段：return ( -_rank(library.open - _delay(library.high, 1)) * _rank(library.open - _delay(library.close, 1)) * _rank(library.open - _delay(library.low, 1)) )
- 本类中的具体角色：文章来源把它概括为“跳空缺口回补”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、high、low、open 的近期变化、历史位置或极值位置转成强弱信号；历史滞后、截面排名 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #020。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha020 / 第 382-387 行；总览匹配行 8353、8654
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha023
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、条件分支、窗口差分、滚动求和、动态生成
- 计算结构：字段 high；算子 conditional、delta、ts_sum；窗口 delta=2、ts_sum=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：最高价均值条件反转；核心算子：sma, delta, high。
- 源码计算片段：return _conditional( _ts_sum(library.high, 20) / 20.0 < library.high, -_delta(library.high, 2), 0.0, )
- 本类中的具体角色：文章来源把它概括为“最高价均值条件反转”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 high 的近期变化、历史位置或极值位置转成强弱信号；条件分支、窗口差分、滚动求和 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 high；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #023。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha023 / 第 405-410 行；总览匹配行 8701
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha024
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、条件分支、历史滞后、窗口差分、滚动最小值、滚动求和、动态生成
- 计算结构：字段 close；算子 conditional、delay、delta、ts_min、ts_sum；窗口 ts_sum=100、delta=100、delay=100、delta=3、ts_min=100；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：收盘价均值条件反转；核心算子：sma, delta, close。
- 源码计算片段：mean100 = _ts_sum(library.close, 100) / 100.0 change = _safe_divide(_delta(mean100, 100), _delay(library.close, 100)) return _conditional( change <= 0.05, -(library.close - _ts_min(library.close, 100)), -_delta(library.close, 3), )
- 本类中的具体角色：文章来源把它概括为“收盘价均值条件反转”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；条件分支、历史滞后、窗口差分、滚动最小值、滚动求和 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #024。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha024 / 第 413-420 行；总览匹配行 8717
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha029
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、历史滞后、窗口差分、log、截面排名、收益序列、动态生成
- 计算结构：字段 close；算子 delay、delta、log、rank、returns、scale、ts_min、ts_product、ts_rank、ts_sum；窗口 ts_min=2、ts_sum=1、delta=5、ts_min=5、ts_rank=5、ts_product=1、delay=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：收盘价变化的排名趋势；核心算子：delta, ts_rank, returns。
- 源码计算片段：delta = _rank(_delta(library.close - 1.0, 5)) inner = _rank(_rank(-delta)) inner = _ts_min(inner, 2) inner = _ts_sum(inner, 1) inner = _scale(np.log(inner)) inner = _rank(_rank(inner)) return _ts_min(_ts_product(inner, 1), 5) + _ts_rank( _delay(-_returns(library), 6), 5 )
- 本类中的具体角色：文章来源把它概括为“收盘价变化的排名趋势”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；历史滞后、窗口差分、log、截面排名、收益序列、截面缩放 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #029。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha029 / 第 457-466 行；总览匹配行 8801
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha030
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、volume、历史滞后、窗口差分、截面排名、sign、动态生成
- 计算结构：字段 close、volume；算子 delay、delta、rank、sign、ts_sum；窗口 ts_sum=20、ts_sum=5、delta=1、delay=2、delay=3、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：价量变化的符号交互；核心算子：delta, close, volume。
- 源码计算片段：sign_sum = ( np.sign(_delta(library.close, 1)) + np.sign(_delay(library.close, 1) - _delay(library.close, 2)) + np.sign(_delay(library.close, 2) - _delay(library.close, 3)) ) return (1.0 - _rank(sign_sum)) * _ts_sum(library.volume, 5) / _ts_sum( library.volume, 20 )
- 本类中的具体角色：文章来源把它概括为“价量变化的符号交互”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、volume 的近期变化、历史位置或极值位置转成强弱信号；历史滞后、窗口差分、截面排名、sign、滚动求和 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close、volume；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #030。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha030 / 第 469-477 行；总览匹配行 8354、8821
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha033
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、open、截面排名、动态生成
- 计算结构：字段 close、open；算子 rank；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：文章逻辑：开收盘价排名反转；核心算子：rank, open/close。
- 源码计算片段：return _rank(-((1.0 - _safe_divide(library.open, library.close)) ** 1))
- 本类中的具体角色：文章来源把它概括为“开收盘价排名反转”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、open 的近期变化、历史位置或极值位置转成强弱信号；截面排名 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close、open；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #033。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha033 / 第 499-500 行；总览匹配行 8875
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha035
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、volume、收益序列、时间序列排名、动态生成
- 计算结构：字段 close、high、low、volume；算子 returns、ts_rank；窗口 ts_rank=32、ts_rank=16；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：多因子复合反转；核心算子：rank, returns, volume, ts_rank。
- 源码计算片段：return ( _ts_rank(library.volume, 32) * (1.0 - _ts_rank(library.close + library.high - library.low, 16)) * (1.0 - _ts_rank(_returns(library), 32)) )
- 本类中的具体角色：文章来源把它概括为“多因子复合反转”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、high、low、volume 的近期变化、历史位置或极值位置转成强弱信号；收益序列、时间序列排名 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #035。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha035 / 第 510-515 行；总览匹配行 8902
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha037
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、open、滚动相关性、历史滞后、截面排名、动态生成
- 计算结构：字段 close、open；算子 correlation、delay、rank；窗口 correlation=200、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：开盘价排名的自相关；核心算子：correlation, rank, delay。
- 源码计算片段：return _rank( _correlation(_delay(library.open - library.close, 1), library.close, 200) ) + _rank(library.open - library.close)
- 本类中的具体角色：文章来源把它概括为“开盘价排名的自相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、open 的近期变化、历史位置或极值位置转成强弱信号；滚动相关性、历史滞后、截面排名 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close、open；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #037。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha037 / 第 533-536 行；总览匹配行 8941
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha038
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、open、截面排名、时间序列排名、动态生成
- 计算结构：字段 close、open；算子 rank、ts_rank；窗口 ts_rank=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：收盘价排名与日内涨幅；核心算子：rank, close, open。
- 源码计算片段：return -_rank(_ts_rank(library.close, 10)) * _rank( _safe_divide(library.close, library.open) )
- 本类中的具体角色：文章来源把它概括为“收盘价排名与日内涨幅”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、open 的近期变化、历史位置或极值位置转成强弱信号；截面排名、时间序列排名 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close、open；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #038。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha038 / 第 539-542 行；总览匹配行 8955
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha039
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、volume、平均成交额/成交量、线性衰减、窗口差分、截面排名、动态生成、字段回退
- 计算结构：字段 close、volume；算子 adv、decay_linear、delta、rank、returns、ts_sum；窗口 ts_sum=250、delta=7、decay_linear=9、adv=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：衰减动量信号；核心算子：rank, delta, decay_linear, returns。
- 源码计算片段：return -_rank( _delta(library.close, 7) * (1.0 - _rank(_decay_linear(_safe_divide(library.volume, _adv(library, 20)), 9))) ) * (1.0 + _rank(_ts_sum(_returns(library), 250)))
- 本类中的具体角色：文章来源把它概括为“衰减动量信号”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、volume 的近期变化、历史位置或极值位置转成强弱信号；平均成交额/成交量、线性衰减、窗口差分、截面排名、收益序列、滚动求和 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close、volume；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #039。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha039 / 第 545-549 行；总览匹配行 8969
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha046
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、条件分支、历史滞后、动态生成
- 计算结构：字段 close；算子 conditional、delay；窗口 delay=20、delay=10、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：条件价格动量；核心算子：delay, delta, close。
- 源码计算片段：value = ( (_delay(library.close, 20) - _delay(library.close, 10)) / 10.0 - (_delay(library.close, 10) - library.close) / 10.0 ) return _conditional( value > 0.25, -1.0, _conditional(value < 0.0, 1.0, -(library.close - _delay(library.close, 1))), )
- 本类中的具体角色：文章来源把它概括为“条件价格动量”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；条件分支、历史滞后 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #046。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha046 / 第 587-596 行；总览匹配行 9067
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha049
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、条件分支、历史滞后、动态生成
- 计算结构：字段 close；算子 conditional、delay；窗口 delay=20、delay=10、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：条件价格反转；核心算子：delta, delay, close。
- 源码计算片段：value = ( (_delay(library.close, 20) - _delay(library.close, 10)) / 10.0 - (_delay(library.close, 10) - library.close) / 10.0 ) return _conditional(value < -0.1, 1.0, -(library.close - _delay(library.close, 1)))
- 本类中的具体角色：文章来源把它概括为“条件价格反转”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；条件分支、历史滞后 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #049。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha049 / 第 618-623 行；总览匹配行 9122
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha051
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、条件分支、历史滞后、动态生成
- 计算结构：字段 close；算子 conditional、delay；窗口 delay=20、delay=10、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：条件延迟反转；核心算子：delta, delay, close。
- 源码计算片段：value = ( (_delay(library.close, 20) - _delay(library.close, 10)) / 10.0 - (_delay(library.close, 10) - library.close) / 10.0 ) return _conditional(value < -0.05, 1.0, -(library.close - _delay(library.close, 1)))
- 本类中的具体角色：文章来源把它概括为“条件延迟反转”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；条件分支、历史滞后 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #051。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha051 / 第 632-637 行；总览匹配行 8357、9152
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha052
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：low、volume、历史滞后、截面排名、收益序列、滚动最小值、动态生成
- 计算结构：字段 low、volume；算子 delay、rank、returns、ts_min、ts_rank、ts_sum；窗口 ts_min=5、ts_rank=5、delay=5、ts_sum=240、ts_sum=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：价格低点 + 成交量排名；核心算子：delta, ts_min, ts_rank, volume。
- 源码计算片段：low_min = _ts_min(library.low, 5) return ( (-low_min + _delay(low_min, 5)) * _rank( (_ts_sum(_returns(library), 240) - _ts_sum(_returns(library), 20)) / 220.0 ) * _ts_rank(library.volume, 5) )
- 本类中的具体角色：文章来源把它概括为“价格低点 + 成交量排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 low、volume 的近期变化、历史位置或极值位置转成强弱信号；历史滞后、截面排名、收益序列、滚动最小值、时间序列排名、滚动求和 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 low、volume；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #052。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha052 / 第 640-648 行；总览匹配行 9168
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha053
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、窗口差分、动态生成
- 计算结构：字段 close、high、low；算子 delta；窗口 delta=9；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：日内位置变化；核心算子：delta, close, high, low。
- 源码计算片段：value = _safe_divide( (library.close - library.low) - (library.high - library.close), library.close - library.low, ) return -_delta(value, 9)
- 本类中的具体角色：文章来源把它概括为“日内位置变化”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、high、low 的近期变化、历史位置或极值位置转成强弱信号；窗口差分 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close、high、low；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #053。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha053 / 第 651-656 行；总览匹配行 9187
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha056
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：open、high、low、close、volume、cap、动态生成、字段回退
- 计算结构：字段 open、high、low、close、volume；算子 cap、rank、returns、ts_sum；窗口 ts_sum=10、ts_sum=3、ts_sum=2；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：市值与收益排名的交互；核心算子：rank, returns, cap。
- 源码计算片段：first = _rank( _safe_divide( _ts_sum(_returns(library), 10), _ts_sum(_ts_sum(_returns(library), 2), 3), ) ) return -first * _rank(_returns(library) * _cap(library))
- 本类中的具体角色：文章来源把它概括为“市值与收益排名的交互”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 open、high、low、close、volume 的近期变化、历史位置或极值位置转成强弱信号；cap、截面排名、收益序列、滚动求和 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 open、high、low、close、volume；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #056。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha056 / 第 672-679 行；总览匹配行 9232
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha084
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、窗口差分、保留符号幂、滚动最大值、时间序列排名、成交量加权价格、动态生成、字段回退
- 计算结构：字段 close；算子 delta、signed_power、ts_max、ts_rank、vwap；窗口 ts_rank=20.7127、delta=4.96796、ts_max=15.3217；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：vwap-close 偏离的幂放大；核心算子：rank, vwap, close, signedpower。
- 源码计算片段：base = _ts_rank( _vwap(library) - _ts_max(_vwap(library), 15.3217), 20.7127 ) return _signed_power(base, _delta(library.close, 4.96796))
- 本类中的具体角色：文章来源把它概括为“vwap-close 偏离的幂放大”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的近期变化、历史位置或极值位置转成强弱信号；窗口差分、保留符号幂、滚动最大值、时间序列排名、成交量加权价格 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #084。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha084 / 第 1037-1041 行；总览匹配行 9821
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha090
- 主分类：动量与反转
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、low、平均成交额/成交量、滚动相关性、行业/分组中性化、截面排名、行业中性化、动态生成
- 计算结构：字段 close、low；算子 adv、correlation、indneutralize、rank、signed_power、ts_max、ts_rank；窗口 ts_rank=3.21856、correlation=5.38375、adv=40、ts_max=4.66719；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：收盘与均量排名相关反转；核心算子：rank, correlation, close, adv。
- 源码计算片段：exponent = _ts_rank( _correlation( _indneutralize(library, _adv(library, 40), "subindustry"), library.low, 5.38375, ), 3.21856, ) return -_signed_power(_rank(library.close - _ts_max(library.close, 4.66719)), exponent)
- 本类中的具体角色：文章来源把它概括为“收盘与均量排名相关反转”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、low 的近期变化、历史位置或极值位置转成强弱信号；平均成交额/成交量、滚动相关性、行业/分组中性化、截面排名、保留符号幂、滚动最大值 决定它更接近趋势延续还是短期反转，不能只按因子名称判断方向。
- 数据依赖与适用场景：依赖 close、low；适合用于趋势延续、价格变化或反转逻辑解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #090。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha090 / 第 1138-1147 行；总览匹配行 8360、9970
- 与因子库总览一致性：mentioned
- 语义置信度：中：文章分类与当前实现标记存在差异

## 流动性与复合

> 因子数量：163；来源分布：alpha_features 80、emotion_indicators 36、worldquant_alpha101 23、trading_lib 22、classic_indicators 1、technical_indicators 1

成交活跃度是否确认价格变化，以及多层量价、波动和流动性信息如何组合。它是 Alpha101 中最容易出现复合算子嵌套的一类。 成交量、成交额和 ADV 的变化被用作资金参与度或交易拥挤度的代理。放量但价格不动可能代表分歧或吸收，缩量可能代表参与度下降；这些是待验证的市场行为假设，不是源码本身证明的收益结论。

常见表达是 adv 条件、volume/adv 比值、delta、ts_rank、correlation、decay_linear、rank 和 IndNeutralize 的组合；先判断流动性状态，再对价格变化进行排名、衰减或行业中性化。 Alpha#7 是典型条件结构：放量时观察过去 7 天价格变化绝对值在 60 天中的排名并保留变化方向，缩量时直接给出固定方向；复杂因子的正负号必须拆开每一层解释。

Alpha#7 把“是否放量”作为状态开关，再把价格变化的历史位置作为强度；Alpha#63、#71、#97 等则进一步叠加 VWAP、ADV、衰减或行业中性化。

边界上，复合因子必须核对每个字段的真实口径、缺失回退、行业分类版本和中性化方式。层数越多，单一经济解释越不可靠，报告只说明结构，不替代分层或样本外验证。

### Alpha158 VMA 公式族（5 个参数变体）

这组因子的共同公式是 `volume.rolling({window}, min_periods=1).mean() / volume`。共同输入字段为 volume，主要算子为 rolling、mean；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“流动性与复合”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_vma5、alpha158_vma10、alpha158_vma20、alpha158_vma30、alpha158_vma60。

**因子：alpha158_vma5**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、滚动窗口、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 VMA 公式族”；本因子参数为 window=5。
- 计算结构：字段 volume；算子 rolling、mean；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VMA5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8027、8033
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vma10**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、滚动窗口、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 VMA 公式族”；本因子参数为 window=10。
- 计算结构：字段 volume；算子 rolling、mean；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VMA10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8037、8043
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vma20**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、滚动窗口、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 VMA 公式族”；本因子参数为 window=20。
- 计算结构：字段 volume；算子 rolling、mean；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VMA20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8047、8053
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vma30**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、滚动窗口、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 VMA 公式族”；本因子参数为 window=30。
- 计算结构：字段 volume；算子 rolling、mean；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VMA30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8057、8063
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vma60**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、滚动窗口、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 VMA 公式族”；本因子参数为 window=60。
- 计算结构：字段 volume；算子 rolling、mean；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VMA60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8067、8073
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 VSUMD 公式族（5 个参数变体）

这组因子的共同公式是 `(positive_volume_sum - negative_volume_sum) / rolling(abs(volume - volume.shift(1)), {window}).sum()`。共同输入字段为 volume，主要算子为 shift、rolling、sum、conditional；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“流动性与复合”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_vsumd5、alpha158_vsumd10、alpha158_vsumd20、alpha158_vsumd30、alpha158_vsumd60。

**因子：alpha158_vsumd5**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMD 公式族”；本因子参数为 window=5。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMD5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8277、8283
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vsumd10**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMD 公式族”；本因子参数为 window=10。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMD10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8287、8293
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vsumd20**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMD 公式族”；本因子参数为 window=20。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMD20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8297、8303
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vsumd30**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMD 公式族”；本因子参数为 window=30。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMD30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8307、8313
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vsumd60**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMD 公式族”；本因子参数为 window=60。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMD60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8317、8323
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 VSUMN 公式族（5 个参数变体）

这组因子的共同公式是 `rolling(negative(volume - volume.shift(1)), {window}).sum() / rolling(abs(volume - volume.shift(1)), {window}).sum()`。共同输入字段为 volume，主要算子为 shift、rolling、sum、conditional；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“流动性与复合”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_vsumn5、alpha158_vsumn10、alpha158_vsumn20、alpha158_vsumn30、alpha158_vsumn60。

**因子：alpha158_vsumn5**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMN 公式族”；本因子参数为 window=5。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMN5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8227、8233
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vsumn10**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMN 公式族”；本因子参数为 window=10。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMN10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8237、8243
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vsumn20**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMN 公式族”；本因子参数为 window=20。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMN20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8247、8253
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vsumn30**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMN 公式族”；本因子参数为 window=30。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMN30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8257、8263
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vsumn60**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMN 公式族”；本因子参数为 window=60。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMN60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8267、8273
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 VSUMP 公式族（5 个参数变体）

这组因子的共同公式是 `rolling(positive(volume - volume.shift(1)), {window}).sum() / rolling(abs(volume - volume.shift(1)), {window}).sum()`。共同输入字段为 volume，主要算子为 shift、rolling、sum、conditional；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“流动性与复合”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_vsump5、alpha158_vsump10、alpha158_vsump20、alpha158_vsump30、alpha158_vsump60。

**因子：alpha158_vsump5**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMP 公式族”；本因子参数为 window=5。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMP5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8177、8183
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vsump10**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMP 公式族”；本因子参数为 window=10。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMP10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8187、8193
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vsump20**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMP 公式族”；本因子参数为 window=20。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMP20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8197、8203
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vsump30**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMP 公式族”；本因子参数为 window=30。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMP30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8207、8213
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vsump60**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、滚动窗口、求和、条件分支、动态生成
- 本条参数差异：沿用上述“Alpha158 VSUMP 公式族”；本因子参数为 window=60。
- 计算结构：字段 volume；算子 shift、rolling、sum、conditional；窗口 shift=1、rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSUMP60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8217、8223
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha360 VOLUME 公式族（60 个参数变体）

这组因子的共同公式是 `volume.shift({day}) / (volume + EPSILON)`。共同输入字段为 volume，主要算子为 shift；参数梯度为 day ∈ {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59}。

族级解读：day 只改变回看距离，字段决定比较的是价格还是成交量；它们不是彼此独立的 360 种经济逻辑。 当前分类为“流动性与复合”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha360_volume0、alpha360_volume1、alpha360_volume2 … alpha360_volume57、alpha360_volume58、alpha360_volume59（共 60 个）。

**因子：alpha360_volume0**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=0。
- 计算结构：字段 volume；算子 shift；窗口 shift=0；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族并取 day=0，形成当前值与当前值自身的基准比；day 增大后才逐步引入更远历史观测点。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME0。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6141、6147
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume1**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=1。
- 计算结构：字段 volume；算子 shift；窗口 shift=1；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=1；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME1。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6151、6157
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume2**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=2。
- 计算结构：字段 volume；算子 shift；窗口 shift=2；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=2；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME2。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6161、6167
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume3**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=3。
- 计算结构：字段 volume；算子 shift；窗口 shift=3；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=3；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME3。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6171、6177
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume4**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=4。
- 计算结构：字段 volume；算子 shift；窗口 shift=4；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=4；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME4。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6181、6187
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume5**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=5。
- 计算结构：字段 volume；算子 shift；窗口 shift=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=5；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6191、6197
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume6**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=6。
- 计算结构：字段 volume；算子 shift；窗口 shift=6；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=6；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME6。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6201、6207
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume7**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=7。
- 计算结构：字段 volume；算子 shift；窗口 shift=7；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=7；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME7。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6211、6217
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume8**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=8。
- 计算结构：字段 volume；算子 shift；窗口 shift=8；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=8；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME8。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6221、6227
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume9**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=9。
- 计算结构：字段 volume；算子 shift；窗口 shift=9；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=9；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME9。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6231、6237
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume10**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=10。
- 计算结构：字段 volume；算子 shift；窗口 shift=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=10；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6241、6247
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume11**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=11。
- 计算结构：字段 volume；算子 shift；窗口 shift=11；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=11；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME11。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6251、6257
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume12**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=12。
- 计算结构：字段 volume；算子 shift；窗口 shift=12；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=12；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME12。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6261、6267
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume13**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=13。
- 计算结构：字段 volume；算子 shift；窗口 shift=13；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=13；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME13。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6271、6277
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume14**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=14。
- 计算结构：字段 volume；算子 shift；窗口 shift=14；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=14；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME14。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6281、6287
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume15**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=15。
- 计算结构：字段 volume；算子 shift；窗口 shift=15；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=15；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME15。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6291、6297
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume16**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=16。
- 计算结构：字段 volume；算子 shift；窗口 shift=16；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=16；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME16。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6301、6307
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume17**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=17。
- 计算结构：字段 volume；算子 shift；窗口 shift=17；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=17；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME17。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6311、6317
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume18**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=18。
- 计算结构：字段 volume；算子 shift；窗口 shift=18；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=18；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME18。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6321、6327
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume19**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=19。
- 计算结构：字段 volume；算子 shift；窗口 shift=19；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=19；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME19。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6331、6337
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume20**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=20。
- 计算结构：字段 volume；算子 shift；窗口 shift=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=20；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6341、6347
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume21**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=21。
- 计算结构：字段 volume；算子 shift；窗口 shift=21；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=21；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME21。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6351、6357
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume22**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=22。
- 计算结构：字段 volume；算子 shift；窗口 shift=22；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=22；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME22。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6361、6367
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume23**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=23。
- 计算结构：字段 volume；算子 shift；窗口 shift=23；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=23；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME23。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6371、6377
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume24**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=24。
- 计算结构：字段 volume；算子 shift；窗口 shift=24；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=24；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME24。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6381、6387
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume25**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=25。
- 计算结构：字段 volume；算子 shift；窗口 shift=25；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=25；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME25。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6391、6397
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume26**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=26。
- 计算结构：字段 volume；算子 shift；窗口 shift=26；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=26；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME26。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6401、6407
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume27**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=27。
- 计算结构：字段 volume；算子 shift；窗口 shift=27；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=27；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME27。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6411、6417
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume28**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=28。
- 计算结构：字段 volume；算子 shift；窗口 shift=28；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=28；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME28。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6421、6427
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume29**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=29。
- 计算结构：字段 volume；算子 shift；窗口 shift=29；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=29；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME29。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6431、6437
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume30**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=30。
- 计算结构：字段 volume；算子 shift；窗口 shift=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=30；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6441、6447
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume31**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=31。
- 计算结构：字段 volume；算子 shift；窗口 shift=31；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=31；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME31。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6451、6457
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume32**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=32。
- 计算结构：字段 volume；算子 shift；窗口 shift=32；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=32；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME32。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6461、6467
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume33**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=33。
- 计算结构：字段 volume；算子 shift；窗口 shift=33；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=33；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME33。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6471、6477
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume34**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=34。
- 计算结构：字段 volume；算子 shift；窗口 shift=34；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=34；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME34。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6481、6487
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume35**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=35。
- 计算结构：字段 volume；算子 shift；窗口 shift=35；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=35；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME35。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6491、6497
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume36**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=36。
- 计算结构：字段 volume；算子 shift；窗口 shift=36；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=36；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME36。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6501、6507
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume37**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=37。
- 计算结构：字段 volume；算子 shift；窗口 shift=37；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=37；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME37。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6511、6517
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume38**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=38。
- 计算结构：字段 volume；算子 shift；窗口 shift=38；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=38；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME38。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6521、6527
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume39**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=39。
- 计算结构：字段 volume；算子 shift；窗口 shift=39；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=39；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME39。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6531、6537
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume40**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=40。
- 计算结构：字段 volume；算子 shift；窗口 shift=40；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=40；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME40。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6541、6547
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume41**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=41。
- 计算结构：字段 volume；算子 shift；窗口 shift=41；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=41；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME41。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6551、6557
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume42**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=42。
- 计算结构：字段 volume；算子 shift；窗口 shift=42；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=42；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME42。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6561、6567
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume43**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=43。
- 计算结构：字段 volume；算子 shift；窗口 shift=43；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=43；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME43。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6571、6577
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume44**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=44。
- 计算结构：字段 volume；算子 shift；窗口 shift=44；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=44；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME44。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6581、6587
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume45**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=45。
- 计算结构：字段 volume；算子 shift；窗口 shift=45；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=45；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME45。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6591、6597
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume46**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=46。
- 计算结构：字段 volume；算子 shift；窗口 shift=46；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=46；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME46。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6601、6607
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume47**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=47。
- 计算结构：字段 volume；算子 shift；窗口 shift=47；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=47；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME47。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6611、6617
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume48**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=48。
- 计算结构：字段 volume；算子 shift；窗口 shift=48；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=48；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME48。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6621、6627
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume49**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=49。
- 计算结构：字段 volume；算子 shift；窗口 shift=49；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=49；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME49。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6631、6637
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume50**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=50。
- 计算结构：字段 volume；算子 shift；窗口 shift=50；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=50；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME50。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6641、6647
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume51**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=51。
- 计算结构：字段 volume；算子 shift；窗口 shift=51；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=51；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME51。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6651、6657
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume52**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=52。
- 计算结构：字段 volume；算子 shift；窗口 shift=52；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=52；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME52。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6661、6667
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume53**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=53。
- 计算结构：字段 volume；算子 shift；窗口 shift=53；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=53；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME53。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6671、6677
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume54**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=54。
- 计算结构：字段 volume；算子 shift；窗口 shift=54；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=54；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME54。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6681、6687
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume55**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=55。
- 计算结构：字段 volume；算子 shift；窗口 shift=55；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=55；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME55。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6691、6697
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume56**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=56。
- 计算结构：字段 volume；算子 shift；窗口 shift=56；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=56；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME56。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6701、6707
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume57**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=57。
- 计算结构：字段 volume；算子 shift；窗口 shift=57；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=57；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME57。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6711、6717
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume58**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=58。
- 计算结构：字段 volume；算子 shift；窗口 shift=58；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=58；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME58。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6721、6727
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha360_volume59**
- 主分类：流动性与复合
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、历史位移、动态生成
- 本条参数差异：沿用上述“Alpha360 VOLUME 公式族”；本因子参数为 day=59。
- 计算结构：字段 volume；算子 shift；窗口 shift=59；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述公式族，只取 day=59；相对于较小的 day，它把历史比较点向更远处移动，改变时间尺度而不改变公式骨架。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准。
- 索引说明：Alpha360 VOLUME59。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 6731、6737
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### mfi
- 主分类：流动性与复合
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、high、low、volume、滚动窗口、历史位移
- 计算结构：字段 close、high、low、volume；算子 rolling、shift、sum、where；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：资金流向指标。
- 源码计算片段："""资金流向指标。""" typical = (self.high + self.low + self.close) / 3 flow = typical * self.volume positive = flow.where(typical > typical.shift(), 0.0).rolling(window).sum() negative = flow.where(typical <= typical.shift(), 0.0).rolling(window).sum() return 100 - 100 / (1 + positive / negative)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、high、low、volume 的滚动窗口、历史位移、求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、high、low、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：资金流向指标。
- 来源证据：Factor/libraries/classic_indicators.py / mfi / 第 171-177 行；总览匹配行 631
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### ar
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 AR：26 日人气指标。
- 源码计算片段："""聚宽 AR：26 日人气指标。""" return self._ar()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 AR：26 日人气指标。
- 来源证据：Factor/libraries/emotion_indicators.py / ar / 第 47-49 行；总览匹配行 2649、2657
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### arbr
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 ARBR：AR 与 BR 的差。
- 源码计算片段："""聚宽 ARBR：AR 与 BR 的差。""" return self._ar() - self._br()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 ARBR：AR 与 BR 的差。
- 来源证据：Factor/libraries/emotion_indicators.py / arbr / 第 51-53 行；总览匹配行 2662、2670
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### atr14
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：均值、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 mean、rolling；窗口 rolling=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 ATR14：14 日真实振幅均值。
- 源码计算片段："""聚宽 ATR14：14 日真实振幅均值。""" return self._true_range().rolling(14).mean()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 ATR14：14 日真实振幅均值。
- 来源证据：Factor/libraries/emotion_indicators.py / atr14 / 第 59-61 行；总览匹配行 2688、2696
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### atr6
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：均值、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 mean、rolling；窗口 rolling=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 ATR6：6 日真实振幅均值。
- 源码计算片段："""聚宽 ATR6：6 日真实振幅均值。""" return self._true_range().rolling(6).mean()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 ATR6：6 日真实振幅均值。
- 来源证据：Factor/libraries/emotion_indicators.py / atr6 / 第 55-57 行；总览匹配行 2675、2683
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### br
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 BR：26 日意愿指标。
- 源码计算片段："""聚宽 BR：26 日意愿指标。""" return self._br()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 BR：26 日意愿指标。
- 来源证据：Factor/libraries/emotion_indicators.py / br / 第 63-65 行；总览匹配行 2701、2709
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### davol10
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 DAVOL10：10 日与 120 日平均换手率之比。
- 源码计算片段："""聚宽 DAVOL10：10 日与 120 日平均换手率之比。""" return self._turnover_mean(10) / self._turnover_mean(120)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 DAVOL10：10 日与 120 日平均换手率之比。
- 来源证据：Factor/libraries/emotion_indicators.py / davol10 / 第 71-73 行；总览匹配行 2727、2735
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### davol20
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 DAVOL20：20 日与 120 日平均换手率之比。
- 源码计算片段："""聚宽 DAVOL20：20 日与 120 日平均换手率之比。""" return self._turnover_mean(20) / self._turnover_mean(120)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 DAVOL20：20 日与 120 日平均换手率之比。
- 来源证据：Factor/libraries/emotion_indicators.py / davol20 / 第 75-77 行；总览匹配行 2740、2748
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### davol5
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 DAVOL5：5 日与 120 日平均换手率之比。
- 源码计算片段："""聚宽 DAVOL5：5 日与 120 日平均换手率之比。""" return self._turnover_mean(5) / self._turnover_mean(120)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 DAVOL5：5 日与 120 日平均换手率之比。
- 来源证据：Factor/libraries/emotion_indicators.py / davol5 / 第 67-69 行；总览匹配行 2714、2722
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### mawvad
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：均值、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 mean、rolling；窗口 rolling=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 MAWVAD：WVAD 的 6 日移动均值。
- 源码计算片段："""聚宽 MAWVAD：WVAD 的 6 日移动均值。""" return self._wvad().rolling(6).mean()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 MAWVAD：WVAD 的 6 日移动均值。
- 来源证据：Factor/libraries/emotion_indicators.py / mawvad / 第 79-81 行；总览匹配行 2753、2761
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### psy
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：close、diff、均值、滚动窗口
- 计算结构：字段 close；算子 diff、mean、rolling；窗口 rolling=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 PSY：12 日上涨天数占比。
- 源码计算片段："""聚宽 PSY：12 日上涨天数占比。""" return (self.close.diff() > 0).rolling(12).mean() * 100
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close 的diff、均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 PSY：12 日上涨天数占比。
- 来源证据：Factor/libraries/emotion_indicators.py / psy / 第 88-90 行；总览匹配行 635、2780、2788
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### turnover_volatility
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：滚动窗口、标准差
- 计算结构：字段 turnover；算子 rolling、std；窗口 rolling=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 turnover_volatility：20 日换手率标准差。
- 源码计算片段："""聚宽 turnover_volatility：20 日换手率标准差。""" return self.turnover.rolling(20).std()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 turnover 的滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 turnover 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 turnover；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 turnover_volatility：20 日换手率标准差。
- 来源证据：Factor/libraries/emotion_indicators.py / turnover_volatility / 第 92-94 行；总览匹配行 2793、2795、2801
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### tvma20
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：amount、均值、滚动窗口
- 计算结构：字段 amount；算子 mean、rolling；窗口 rolling=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 TVMA20：20 日成交金额移动均值。
- 源码计算片段："""聚宽 TVMA20：20 日成交金额移动均值。""" return self.amount.rolling(20).mean()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 amount 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 amount 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 amount；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 TVMA20：20 日成交金额移动均值。
- 来源证据：Factor/libraries/emotion_indicators.py / tvma20 / 第 100-102 行；总览匹配行 2819、2827
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### tvma6
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：amount、均值、滚动窗口
- 计算结构：字段 amount；算子 mean、rolling；窗口 rolling=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 TVMA6：6 日成交金额移动均值。
- 源码计算片段："""聚宽 TVMA6：6 日成交金额移动均值。""" return self.amount.rolling(6).mean()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 amount 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 amount 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 amount；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 TVMA6：6 日成交金额移动均值。
- 来源证据：Factor/libraries/emotion_indicators.py / tvma6 / 第 96-98 行；总览匹配行 2806、2814
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### tvstd20
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：amount、滚动窗口、标准差
- 计算结构：字段 amount；算子 rolling、std；窗口 rolling=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 TVSTD20：20 日成交金额标准差。
- 源码计算片段："""聚宽 TVSTD20：20 日成交金额标准差。""" return self.amount.rolling(20).std()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 amount 的滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 amount 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 amount；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 TVSTD20：20 日成交金额标准差。
- 来源证据：Factor/libraries/emotion_indicators.py / tvstd20 / 第 108-110 行；总览匹配行 2845、2853
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### tvstd6
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：amount、滚动窗口、标准差
- 计算结构：字段 amount；算子 rolling、std；窗口 rolling=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 TVSTD6：6 日成交金额标准差。
- 源码计算片段："""聚宽 TVSTD6：6 日成交金额标准差。""" return self.amount.rolling(6).std()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 amount 的滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 amount 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 amount；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 TVSTD6：6 日成交金额标准差。
- 来源证据：Factor/libraries/emotion_indicators.py / tvstd6 / 第 104-106 行；总览匹配行 2832、2840
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vdea
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：ewm、均值
- 计算结构：字段 未从局部源码提取；算子 ewm、mean；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VDEA：VDIFF 的 9 日指数移动均线。
- 源码计算片段："""聚宽 VDEA：VDIFF 的 9 日指数移动均线。""" return self._vdiff().ewm(span=9, adjust=False).mean()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VDEA：VDIFF 的 9 日指数移动均线。
- 来源证据：Factor/libraries/emotion_indicators.py / vdea / 第 112-114 行；总览匹配行 2858、2866、2946
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vdiff
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VDIFF：12 日与 26 日成交量 EMA 之差。
- 源码计算片段："""聚宽 VDIFF：12 日与 26 日成交量 EMA 之差。""" return self._vdiff()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VDIFF：12 日与 26 日成交量 EMA 之差。
- 来源证据：Factor/libraries/emotion_indicators.py / vdiff / 第 116-118 行；总览匹配行 2871、2879
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vema10
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VEMA10：10 日成交量指数移动均线。
- 源码计算片段："""聚宽 VEMA10：10 日成交量指数移动均线。""" return self._vema(10)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VEMA10：10 日成交量指数移动均线。
- 来源证据：Factor/libraries/emotion_indicators.py / vema10 / 第 124-126 行；总览匹配行 2897、2905
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vema12
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VEMA12：12 日成交量指数移动均线。
- 源码计算片段："""聚宽 VEMA12：12 日成交量指数移动均线。""" return self._vema(12)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VEMA12：12 日成交量指数移动均线。
- 来源证据：Factor/libraries/emotion_indicators.py / vema12 / 第 128-130 行；总览匹配行 2910、2918
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vema26
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VEMA26：26 日成交量指数移动均线。
- 源码计算片段："""聚宽 VEMA26：26 日成交量指数移动均线。""" return self._vema(26)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VEMA26：26 日成交量指数移动均线。
- 来源证据：Factor/libraries/emotion_indicators.py / vema26 / 第 132-134 行；总览匹配行 2923、2931
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vema5
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VEMA5：5 日成交量指数移动均线。
- 源码计算片段："""聚宽 VEMA5：5 日成交量指数移动均线。""" return self._vema(5)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VEMA5：5 日成交量指数移动均线。
- 来源证据：Factor/libraries/emotion_indicators.py / vema5 / 第 120-122 行；总览匹配行 2884、2892
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vmacd
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VMACD：成交量 MACD 柱值。
- 源码计算片段："""聚宽 VMACD：成交量 MACD 柱值。""" return self._vdiff() - self.vdea()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VMACD：成交量 MACD 柱值。
- 来源证据：Factor/libraries/emotion_indicators.py / vmacd / 第 136-138 行；总览匹配行 646、2936、2944
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vol10
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VOL10：10 日平均换手率。
- 源码计算片段："""聚宽 VOL10：10 日平均换手率。""" return self._turnover_mean(10)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VOL10：10 日平均换手率。
- 来源证据：Factor/libraries/emotion_indicators.py / vol10 / 第 144-146 行；总览匹配行 2962、2970
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vol120
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VOL120：120 日平均换手率。
- 源码计算片段："""聚宽 VOL120：120 日平均换手率。""" return self._turnover_mean(120)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VOL120：120 日平均换手率。
- 来源证据：Factor/libraries/emotion_indicators.py / vol120 / 第 156-158 行；总览匹配行 3001、3009
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vol20
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VOL20：20 日平均换手率。
- 源码计算片段："""聚宽 VOL20：20 日平均换手率。""" return self._turnover_mean(20)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VOL20：20 日平均换手率。
- 来源证据：Factor/libraries/emotion_indicators.py / vol20 / 第 148-150 行；总览匹配行 2975、2983
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vol240
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VOL240：240 日平均换手率。
- 源码计算片段："""聚宽 VOL240：240 日平均换手率。""" return self._turnover_mean(240)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VOL240：240 日平均换手率。
- 来源证据：Factor/libraries/emotion_indicators.py / vol240 / 第 160-162 行；总览匹配行 3014、3022
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vol5
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VOL5：5 日平均换手率。
- 源码计算片段："""聚宽 VOL5：5 日平均换手率。""" return self._turnover_mean(5)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VOL5：5 日平均换手率。
- 来源证据：Factor/libraries/emotion_indicators.py / vol5 / 第 140-142 行；总览匹配行 2949、2957
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vol60
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VOL60：60 日平均换手率。
- 源码计算片段："""聚宽 VOL60：60 日平均换手率。""" return self._turnover_mean(60)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VOL60：60 日平均换手率。
- 来源证据：Factor/libraries/emotion_indicators.py / vol60 / 第 152-154 行；总览匹配行 2988、2996
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vosc
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 VOSC：成交量震荡指标。
- 源码计算片段："""聚宽 VOSC：成交量震荡指标。""" return (self._vema(12) - self._vema(26)) / self._vema(12) * 100
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VOSC：成交量震荡指标。
- 来源证据：Factor/libraries/emotion_indicators.py / vosc / 第 164-166 行；总览匹配行 647、3027、3035
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vr
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：close、volume、diff、滚动窗口、求和、where
- 计算结构：字段 close、volume；算子 diff、rolling、sum、where；窗口 rolling=26；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 VR：成交量比率。
- 源码计算片段："""聚宽 VR：成交量比率。""" change = self.close.diff() up = self.volume.where(change > 0, 0.0) down = self.volume.where(change < 0, 0.0) flat = self.volume.where(change == 0, 0.0) return (up.rolling(26).sum() + flat.rolling(26).sum() / 2) / ( down.rolling(26).sum() + flat.rolling(26).sum() / 2 )
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、volume 的diff、滚动窗口、求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 VR：成交量比率。
- 来源证据：Factor/libraries/emotion_indicators.py / vr / 第 168-176 行；总览匹配行 3040、3048
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vroc12
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：volume、收益变化
- 计算结构：字段 volume；算子 pct_change；窗口 pct_change=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 VROC12：12 日成交量变动速率。
- 源码计算片段："""聚宽 VROC12：12 日成交量变动速率。""" return self.volume.pct_change(12) * 100
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 volume 的收益变化实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VROC12：12 日成交量变动速率。
- 来源证据：Factor/libraries/emotion_indicators.py / vroc12 / 第 182-184 行；总览匹配行 3072、3080
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vroc6
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：volume、收益变化
- 计算结构：字段 volume；算子 pct_change；窗口 pct_change=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 VROC6：6 日成交量变动速率。
- 源码计算片段："""聚宽 VROC6：6 日成交量变动速率。""" return self.volume.pct_change(6) * 100
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 volume 的收益变化实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 VROC6：6 日成交量变动速率。
- 来源证据：Factor/libraries/emotion_indicators.py / vroc6 / 第 178-180 行；总览匹配行 3059、3067
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vstd10
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：volume、滚动窗口、标准差
- 计算结构：字段 volume；算子 rolling、std；窗口 rolling=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 VSTD10：10 日成交量标准差。
- 源码计算片段："""聚宽 VSTD10：10 日成交量标准差。""" return self.volume.rolling(10).std()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 volume 的滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 VSTD10：10 日成交量标准差。
- 来源证据：Factor/libraries/emotion_indicators.py / vstd10 / 第 186-188 行；总览匹配行 3085、3093
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vstd20
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：volume、滚动窗口、标准差
- 计算结构：字段 volume；算子 rolling、std；窗口 rolling=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 VSTD20：20 日成交量标准差。
- 源码计算片段："""聚宽 VSTD20：20 日成交量标准差。""" return self.volume.rolling(20).std()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 volume 的滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 VSTD20：20 日成交量标准差。
- 来源证据：Factor/libraries/emotion_indicators.py / vstd20 / 第 190-192 行；总览匹配行 3098、3106
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### wvad
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 WVAD：6 日威廉变异离散量。
- 源码计算片段："""聚宽 WVAD：6 日威廉变异离散量。""" return self._wvad()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 WVAD：6 日威廉变异离散量。
- 来源证据：Factor/libraries/emotion_indicators.py / wvad / 第 194-196 行；总览匹配行 653、3111、3119
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### money_flow_20
- 主分类：流动性与复合
- 因子库来源：emotion_indicators（情绪、成交量和波动派生指标）
- 辅助标签：close、high、low、volume、滚动窗口、求和
- 计算结构：字段 close、high、low、volume；算子 rolling、sum；窗口 rolling=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 money_flow_20：20 日典型价格资金流量。
- 源码计算片段："""聚宽 money_flow_20：20 日典型价格资金流量。""" typical_price = (self.high + self.low + self.close) / 3 return (typical_price * self.volume).rolling(20).sum()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、high、low、volume 的滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、high、low、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 money_flow_20：20 日典型价格资金流量。
- 来源证据：Factor/libraries/emotion_indicators.py / money_flow_20 / 第 83-86 行；总览匹配行 2766、2768、2774
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### mfi14
- 主分类：流动性与复合
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、high、low、volume、滚动窗口、历史位移
- 计算结构：字段 close、high、low、volume；算子 rolling、shift、sum、where；窗口 rolling=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 MFI14：14 日资金流量指标。
- 源码计算片段："""聚宽 MFI14：14 日资金流量指标。""" typical_price = (self.high + self.low + self.close) / 3 money_flow = typical_price * self.volume positive = money_flow.where(typical_price > typical_price.shift(), 0.0) negative = money_flow.where(typical_price < typical_price.shift(), 0.0) money_ratio = positive.rolling(14).sum() / negative.rolling(14).sum() return 100 - 100 / (1 + money_ratio)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、high、low、volume 的滚动窗口、历史位移、求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、high、low、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 MFI14：14 日资金流量指标。
- 来源证据：Factor/libraries/technical_indicators.py / mfi14 / 第 75-82 行；总览匹配行 2410、2418
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### chaikin_money_flow
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：close、high、low、volume、滚动窗口、求和
- 计算结构：字段 close、high、low、volume；算子 rolling、sum；窗口 window=21；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：Chaikin 资金流：量价累积/派发在窗口内的成交量加权均值。
- 源码计算片段："""Chaikin 资金流：量价累积/派发在窗口内的成交量加权均值。""" multiplier = ((self.close - self.low) - (self.high - self.close)) / ( self.high - self.low + 1e-10 ) return ( (multiplier * self.volume).rolling(window).sum() / self.volume.rolling(window).sum() )
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、high、low、volume 的滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、high、low、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：Chaikin 资金流：量价累积/派发在窗口内的成交量加权均值。
- 来源证据：Factor/libraries/trading_lib.py / chaikin_money_flow / 第 113-121 行；总览匹配行 2145、2152
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### chaikin_oscillator
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：close、high、low、volume、ewm、均值
- 计算结构：字段 close、high、low、volume；算子 ewm、mean；窗口 fast=3、slow=10；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：Chaikin Oscillator：累积/派发线的快慢 EMA 差。
- 源码计算片段："""Chaikin Oscillator：累积/派发线的快慢 EMA 差。""" multiplier = ((self.close - self.low) - (self.high - self.close)) / ( self.high - self.low + 1e-10 ) accumulation_distribution = (multiplier * self.volume).cumsum() return ( accumulation_distribution.ewm(span=fast, adjust=False).mean() - accumulation_distribution.ewm(span=slow, adjust=False).mean() )
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、high、low、volume 的ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、high、low、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点
- 索引说明：Chaikin Oscillator：累积/派发线的快慢 EMA 差。
- 来源证据：Factor/libraries/trading_lib.py / chaikin_oscillator / 第 137-146 行；总览匹配行 2187、2194
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### money_flow
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：close、volume、收益变化、滚动窗口、求和
- 计算结构：字段 close、volume；算子 pct_change、rolling、sum；窗口 window=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：资金流：价格变动 × 成交量。
- 源码计算片段："""资金流：价格变动 × 成交量。""" ret = self.close.pct_change() return (ret * self.volume).rolling(window).sum()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、volume 的收益变化、滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：资金流：价格变动 × 成交量。
- 来源证据：Factor/libraries/trading_lib.py / money_flow / 第 91-94 行；总览匹配行 2101、2109、2421
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### negative_volume_index
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：close、volume、收益变化、历史位移、where
- 计算结构：字段 close、volume；算子 pct_change、shift、where；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：负量指标：仅在成交量减少时累计收盘收益。
- 源码计算片段："""负量指标：仅在成交量减少时累计收盘收益。""" factor = (1 + self.close.pct_change()).where( self.volume < self.volume.shift(), 1.0 ).fillna(1.0) return base_value * factor.cumprod()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、volume 的收益变化、历史位移、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：负量指标：仅在成交量减少时累计收盘收益。
- 来源证据：Factor/libraries/trading_lib.py / negative_volume_index / 第 130-135 行；总览匹配行 2173、2180
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### net_buy_ratio
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：close、volume、clip、收益变化、滚动窗口、求和
- 计算结构：字段 close、volume；算子 clip、pct_change、rolling、sum；窗口 window=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：净买入比。
- 源码计算片段："""净买入比。""" ret = self.close.pct_change() buy_vol = ret.clip(lower=0) * self.volume sell_vol = (-ret).clip(lower=0) * self.volume buy_sum = buy_vol.rolling(window).sum() sell_sum = sell_vol.rolling(window).sum() return (buy_sum - sell_sum) / (buy_sum + sell_sum + 1e-10)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、volume 的clip、收益变化、滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：净买入比。
- 来源证据：Factor/libraries/trading_lib.py / net_buy_ratio / 第 96-103 行；总览匹配行 2115、2123
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### obv
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：close、volume、diff
- 计算结构：字段 close、volume；算子 diff；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：能量潮：按收盘涨跌累计成交量，起始值为 0。
- 源码计算片段："""能量潮：按收盘涨跌累计成交量，起始值为 0。""" direction = ( self.close.diff().gt(0).astype(float) - self.close.diff().lt(0).astype(float) ) return (direction * self.volume).cumsum()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、volume 的diff实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：能量潮：按收盘涨跌累计成交量，起始值为 0。
- 来源证据：Factor/libraries/trading_lib.py / obv / 第 105-111 行；总览匹配行 2133、2140
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### positive_volume_index
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：close、volume、收益变化、历史位移、where
- 计算结构：字段 close、volume；算子 pct_change、shift、where；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：正量指标：仅在成交量增加时累计收盘收益。
- 源码计算片段："""正量指标：仅在成交量增加时累计收盘收益。""" factor = (1 + self.close.pct_change()).where( self.volume > self.volume.shift(), 1.0 ).fillna(1.0) return base_value * factor.cumprod()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、volume 的收益变化、历史位移、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：正量指标：仅在成交量增加时累计收盘收益。
- 来源证据：Factor/libraries/trading_lib.py / positive_volume_index / 第 123-128 行；总览匹配行 2159、2166
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### turnover_std
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：滚动窗口、标准差
- 计算结构：字段 turnover；算子 rolling、std；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：换手率波动。
- 源码计算片段："""换手率波动。""" return self.turnover.rolling(window).std()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 turnover 的滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 turnover 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 turnover；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：换手率波动。
- 来源证据：Factor/libraries/trading_lib.py / turnover_std / 第 59-61 行；总览匹配行 2028、2036
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### volume_confirmation
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：close、volume、均值、收益变化、滚动窗口
- 计算结构：字段 close、volume；算子 mean、pct_change、rolling；窗口 window=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：量能确认：上涨时放量，下跌时缩量。
- 源码计算片段："""量能确认：上涨时放量，下跌时缩量。""" ret = self.close.pct_change() vol_ratio = self.volume / self.volume.rolling(window).mean() return ret * vol_ratio
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、volume 的均值、收益变化、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：量能确认：上涨时放量，下跌时缩量。
- 来源证据：Factor/libraries/trading_lib.py / volume_confirmation / 第 71-75 行；总览匹配行 2056、2064
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### volume_divergence
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：close、volume、滚动最大值、均值、滚动窗口
- 计算结构：字段 close、volume；算子 max、mean、rolling；窗口 window=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：量价背离：价格创新高但量能没跟上。
- 源码计算片段："""量价背离：价格创新高但量能没跟上。""" price_high = self.close == self.close.rolling(window).max() vol_avg = self.volume / self.volume.rolling(window).mean() return (price_high.astype(float) * (1 - vol_avg)) * (-1)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、volume 的滚动最大值、均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：量价背离：价格创新高但量能没跟上。
- 来源证据：Factor/libraries/trading_lib.py / volume_divergence / 第 83-87 行；总览匹配行 2086、2094
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### volume_oscillator
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：volume、均值、滚动窗口
- 计算结构：字段 volume；算子 mean、rolling；窗口 short=5、long=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：成交量振荡器：短期与长期平均成交量的百分比差。
- 源码计算片段："""成交量振荡器：短期与长期平均成交量的百分比差。""" short_average = self.volume.rolling(short).mean() long_average = self.volume.rolling(long).mean() return (short_average / (long_average + 1e-10) - 1) * 100
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 volume 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：成交量振荡器：短期与长期平均成交量的百分比差。
- 来源证据：Factor/libraries/trading_lib.py / volume_oscillator / 第 148-152 行；总览匹配行 2205、2212
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### volume_price_corr
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：close、volume、滚动相关性、收益变化、滚动窗口
- 计算结构：字段 close、volume；算子 corr、pct_change、rolling；窗口 window=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：量价相关性：成交量和价格的相关系数。
- 源码计算片段："""量价相关性：成交量和价格的相关系数。""" ret = self.close.pct_change() vol = self.volume.pct_change() return ret.rolling(window).corr(vol)
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、volume 的滚动相关性、收益变化、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：量价相关性：成交量和价格的相关系数。
- 来源证据：Factor/libraries/trading_lib.py / volume_price_corr / 第 65-69 行；总览匹配行 2041、2049
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### volume_price_trend
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：close、volume、均值、滚动窗口
- 计算结构：字段 close、volume；算子 mean、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：量价趋势：价格趋势 × 量能趋势。
- 源码计算片段："""量价趋势：价格趋势 × 量能趋势。""" price_trend = self.close / self.close.rolling(window).mean() - 1 vol_trend = self.volume / self.volume.rolling(window).mean() - 1 return price_trend * vol_trend
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 close、volume 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：量价趋势：价格趋势 × 量能趋势。
- 来源证据：Factor/libraries/trading_lib.py / volume_price_trend / 第 77-81 行；总览匹配行 2071、2079
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### volume_shock
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：volume、滚动最小值、滚动窗口
- 计算结构：字段 volume；算子 min、rolling；窗口 window=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：成交量突变：当日量 / 前 window 日最小量。
- 源码计算片段："""成交量突变：当日量 / 前 window 日最小量。""" return self.volume / self.volume.rolling(window).min()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 volume 的滚动最小值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：成交量突变：当日量 / 前 window 日最小量。
- 来源证据：Factor/libraries/trading_lib.py / volume_shock / 第 35-37 行；总览匹配行 1963、1971
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### volume_std
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：volume、均值、滚动窗口、标准差
- 计算结构：字段 volume；算子 mean、rolling、std；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：成交量波动：成交量的 ZSCORE。
- 源码计算片段："""成交量波动：成交量的 ZSCORE。""" vol = self.volume return (vol - vol.rolling(window).mean()) / vol.rolling(window).std()
- 本类中的具体角色：它在“流动性与复合”总论中具体通过 volume 的均值、滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：成交量波动：成交量的 ZSCORE。
- 来源证据：Factor/libraries/trading_lib.py / volume_std / 第 30-33 行；总览匹配行 1949、1957
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### amount 公式族（2 个参数变体）

这组因子的共同公式是 `self.amount / self.amount.rolling(window).mean()`。共同输入字段为 amount，主要算子为 mean、rolling；参数梯度为 window ∈ {5, 20}。

族级解读：共同公式比较当前成交额与其 window 日均值，窗口改变流动性基准的观察尺度。 当前分类为“流动性与复合”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：amount_5d、amount_20d。

**因子：amount_5d**
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：amount、均值、滚动窗口
- 本条参数差异：沿用上述“amount 公式族”；本因子参数为 window=5。
- 计算结构：字段 amount；算子 mean、rolling；窗口 window=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=5；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 amount；滚动窗口前置样本不足时会产生空值。
- 索引说明：5 日成交额比。
- 来源证据：Factor/libraries/trading_lib.py / amount_5d / 第 41-43 行；总览匹配行 1976、1984
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：amount_20d**
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：amount、均值、滚动窗口
- 本条参数差异：沿用上述“amount 公式族”；本因子参数为 window=20。
- 计算结构：字段 amount；算子 mean、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=20；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 amount；滚动窗口前置样本不足时会产生空值。
- 索引说明：20 日成交额比。
- 来源证据：Factor/libraries/trading_lib.py / amount_20d / 第 45-47 行；总览匹配行 1989、1997
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### turnover 公式族（2 个参数变体）

这组因子的共同公式是 `self.turnover.rolling(window).mean()`。共同输入字段为 turnover，主要算子为 mean、rolling；参数梯度为 window ∈ {5, 20}。

族级解读：共同公式使用 window 日换手率均值，窗口改变流动性状态的平滑程度。 当前分类为“流动性与复合”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：turnover_5d、turnover_20d。

**因子：turnover_5d**
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：均值、滚动窗口
- 本条参数差异：沿用上述“turnover 公式族”；本因子参数为 window=5。
- 计算结构：字段 turnover；算子 mean、rolling；窗口 window=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=5；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 turnover；滚动窗口前置样本不足时会产生空值。
- 索引说明：5 日平均换手率。
- 来源证据：Factor/libraries/trading_lib.py / turnover_5d / 第 51-53 行；总览匹配行 2002、2010
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：turnover_20d**
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：均值、滚动窗口
- 本条参数差异：沿用上述“turnover 公式族”；本因子参数为 window=20。
- 计算结构：字段 turnover；算子 mean、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=20；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 turnover；滚动窗口前置样本不足时会产生空值。
- 索引说明：20 日平均换手率。
- 来源证据：Factor/libraries/trading_lib.py / turnover_20d / 第 55-57 行；总览匹配行 2015、2023
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### volume 公式族（3 个参数变体）

这组因子的共同公式是 `self.volume / self.volume.rolling(window).mean()`。共同输入字段为 volume，主要算子为 mean、rolling；参数梯度为 window ∈ {5, 20, 60}。

族级解读：共同公式比较当前成交量与其 window 日均值，窗口改变成交活跃度基准的观察尺度。 当前分类为“流动性与复合”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：volume_5d、volume_20d、volume_60d。

**因子：volume_5d**
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：volume、均值、滚动窗口
- 本条参数差异：沿用上述“volume 公式族”；本因子参数为 window=5。
- 计算结构：字段 volume；算子 mean、rolling；窗口 window=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=5；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 volume；滚动窗口前置样本不足时会产生空值。
- 索引说明：5 日均量：成交量 / 过去 window 日均量。
- 来源证据：Factor/libraries/trading_lib.py / volume_5d / 第 18-20 行；总览匹配行 1910、1918
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：volume_20d**
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：volume、均值、滚动窗口
- 本条参数差异：沿用上述“volume 公式族”；本因子参数为 window=20。
- 计算结构：字段 volume；算子 mean、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=20；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 volume；滚动窗口前置样本不足时会产生空值。
- 索引说明：20 日均量。
- 来源证据：Factor/libraries/trading_lib.py / volume_20d / 第 22-24 行；总览匹配行 1923、1931
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：volume_60d**
- 主分类：流动性与复合
- 因子库来源：trading_lib（量价、资金流与成交确认）
- 辅助标签：volume、均值、滚动窗口
- 本条参数差异：沿用上述“volume 公式族”；本因子参数为 window=60。
- 计算结构：字段 volume；算子 mean、rolling；窗口 window=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=60；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 volume；滚动窗口前置样本不足时会产生空值。
- 索引说明：60 日均量。
- 来源证据：Factor/libraries/trading_lib.py / volume_60d / 第 26-28 行；总览匹配行 1936、1944
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### alpha007
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、volume、abs、平均成交额/成交量、条件分支、窗口差分、动态生成、字段回退
- 计算结构：字段 close、volume；算子 abs、adv、conditional、delta、sign、ts_rank；窗口 delta=7、ts_rank=60、adv=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：放量/缩量条件下的价格动量；核心算子：adv, ts_rank, delta。
- 源码计算片段：delta = _delta(library.close, 7) value = -_ts_rank(delta.abs(), 60) * np.sign(delta) return _conditional(_adv(library, 20) < library.volume, value, -1.0)
- 本类中的具体角色：文章来源把它概括为“放量/缩量条件下的价格动量”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #007。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha007 / 第 295-298 行；总览匹配行 8463
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha031
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、low、平均成交额/成交量、滚动相关性、线性衰减、窗口差分、动态生成、字段回退
- 计算结构：字段 close、low；算子 adv、correlation、decay_linear、delta、rank、scale、sign；窗口 delta=3、correlation=12、decay_linear=10、adv=20、delta=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：流动性 + 量价衰减相关；核心算子：rank, adv, correlation, decay_linear。
- 源码计算片段：first = _rank( _rank( _rank( _decay_linear(-_rank(_rank(_delta(library.close, 10))), 10) ) ) ) second = _rank(-_delta(library.close, 3)) third = np.sign(_scale(_correlation(_adv(library, 20), library.low, 12))) return first + second + third
- 本类中的具体角色：文章来源把它概括为“流动性 + 量价衰减相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、low 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、low；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #031。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha031 / 第 480-490 行；总览匹配行 8355、8840
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha048
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、滚动相关性、历史滞后、窗口差分、行业/分组中性化、滚动求和、行业中性化、动态生成
- 计算结构：字段 close；算子 correlation、delay、delta、indneutralize、ts_sum；窗口 delta=1、ts_sum=250、delay=1、correlation=250；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：行业中性量价相关；核心算子：correlation, rank, delta。
- 源码计算片段：delta = _delta(library.close, 1) delayed_delta = _delta(_delay(library.close, 1), 1) numerator = _correlation(delta, delayed_delta, 250) * delta / library.close denominator = _ts_sum(_safe_divide(delta, _delay(library.close, 1)) ** 2, 250) return _safe_divide(_indneutralize(library, numerator, "subindustry"), denominator)
- 本类中的具体角色：文章来源把它概括为“行业中性量价相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #048。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha048 / 第 610-615 行；总览匹配行 9106
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha058
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：volume、滚动相关性、线性衰减、行业/分组中性化、时间序列排名、成交量加权价格、行业中性化、动态生成
- 计算结构：字段 volume；算子 correlation、decay_linear、indneutralize、ts_rank、vwap；窗口 correlation=3.92795、ts_rank=5.50322、decay_linear=7.89291；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：行业中性量价相关；核心算子：correlation, rank, volume。
- 源码计算片段：value = _correlation( _indneutralize(library, _vwap(library), "sector"), library.volume, 3.92795 ) return -_ts_rank(_decay_linear(value, 7.89291), 5.50322)
- 本类中的具体角色：文章来源把它概括为“行业中性量价相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #058。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha058 / 第 690-694 行；总览匹配行 9266
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha059
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：volume、滚动相关性、线性衰减、行业/分组中性化、时间序列排名、成交量加权价格、行业中性化、动态生成
- 计算结构：字段 volume；算子 correlation、decay_linear、indneutralize、ts_rank、vwap；窗口 correlation=4.25197、ts_rank=8.19648、decay_linear=16.2289；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：行业中性量价相关变体；核心算子：correlation, rank, volume。
- 源码计算片段：vwap = _vwap(library) neutralized = _indneutralize(library, vwap * 0.728317 + vwap * (1 - 0.728317), "industry") value = _correlation(neutralized, library.volume, 4.25197) return -_ts_rank(_decay_linear(value, 16.2289), 8.19648)
- 本类中的具体角色：文章来源把它概括为“行业中性量价相关变体”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #059。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha059 / 第 697-701 行；总览匹配行 9281
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha061
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：open、high、low、close、volume、平均成交额/成交量、动态生成、字段回退
- 计算结构：字段 open、high、low、close、volume；算子 adv、correlation、rank、ts_min、vwap；窗口 correlation=17.9282、ts_min=16.1219、adv=180；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：vwap 排名与均量排名较量；核心算子：rank, vwap, adv。
- 源码计算片段：vwap = _vwap(library) return _bool_signal( _rank(vwap - _ts_min(vwap, 16.1219)) < _rank(_correlation(vwap, _adv(library, 180), 17.9282)) )
- 本类中的具体角色：文章来源把它概括为“vwap 排名与均量排名较量”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 open、high、low、close、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 open、high、low、close、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #061。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha061 / 第 716-721 行；总览匹配行 8358、9316
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha063
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、open、平均成交额/成交量、滚动相关性、线性衰减、窗口差分、行业中性化、动态生成
- 计算结构：字段 close、open；算子 adv、correlation、decay_linear、delta、indneutralize、rank、ts_sum、vwap；窗口 decay_linear=8.22237、decay_linear=12.2883、delta=2.25164、correlation=13.557、ts_sum=37.2467、adv=180；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：流动性衰减信号；核心算子：rank, vwap, delta, decay_linear, adv。
- 源码计算片段：vwap = _vwap(library) left = _rank( _decay_linear( _delta(_indneutralize(library, library.close, "industry"), 2.25164), 8.22237, ) ) right = _rank( _decay_linear( _correlation( vwap * 0.318108 + library.open * (1 - 0.318108), _ts_sum(_adv(library, 180), 37.2467), 13.557, ), 12.2883, ) ) return -(left - right)
- 本类中的具体角色：文章来源把它概括为“流动性衰减信号”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、open 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、open；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #063。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha063 / 第 735-753 行；总览匹配行 9351
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha067
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、平均成交额/成交量、滚动相关性、行业/分组中性化、截面排名、保留符号幂、行业中性化、动态生成
- 计算结构：字段 high；算子 adv、correlation、indneutralize、rank、signed_power、ts_min、vwap；窗口 correlation=6.02936、ts_min=2.14593、adv=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：最高价与均量的相关排名；核心算子：rank, correlation, high, adv。
- 源码计算片段：left = _rank(library.high - _ts_min(library.high, 2.14593)) right = _rank( _correlation( _indneutralize(library, _vwap(library), "sector"), _indneutralize(library, _adv(library, 20), "subindustry"), 6.02936, ) ) return -_signed_power(left, right)
- 本类中的具体角色：文章来源把它概括为“最高价与均量的相关排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 high 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 high；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #067。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha067 / 第 791-800 行；总览匹配行 9439
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha069
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、平均成交额/成交量、滚动相关性、窗口差分、行业/分组中性化、截面排名、行业中性化、动态生成
- 计算结构：字段 close；算子 adv、correlation、delta、indneutralize、rank、signed_power、ts_max、ts_rank、vwap；窗口 ts_rank=9.0615、ts_max=4.79344、correlation=4.92416、delta=2.72412、adv=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：行业中性价格动量排名；核心算子：rank, ts_rank, delta, close, adv。
- 源码计算片段：vwap = _vwap(library) left = _rank( _ts_max( _delta(_indneutralize(library, vwap, "industry"), 2.72412), 4.79344, ) ) exponent = _ts_rank( _correlation( library.close * 0.490655 + vwap * (1 - 0.490655), _adv(library, 20), 4.92416, ), 9.0615, ) return -_signed_power(left, exponent)
- 本类中的具体角色：文章来源把它概括为“行业中性价格动量排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #069。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha069 / 第 814-830 行；总览匹配行 9478
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha070
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、平均成交额/成交量、滚动相关性、窗口差分、行业/分组中性化、截面排名、行业中性化、动态生成
- 计算结构：字段 close；算子 adv、correlation、delta、indneutralize、rank、signed_power、ts_rank、vwap；窗口 ts_rank=17.9171、correlation=17.8256、adv=50、delta=1.29456；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：行业中性价格-vwap 变化；核心算子：rank, delta, close, vwap。
- 源码计算片段：exponent = _ts_rank( _correlation( _indneutralize(library, library.close, "industry"), _adv(library, 50), 17.8256, ), 17.9171, ) return -_signed_power(_rank(_delta(_vwap(library), 1.29456)), exponent)
- 本类中的具体角色：文章来源把它概括为“行业中性价格-vwap 变化”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #070。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha070 / 第 833-842 行；总览匹配行 8358、9505
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha071
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、low、open、平均成交额/成交量、滚动相关性、线性衰减、动态生成、字段回退
- 计算结构：字段 close、low、open；算子 adv、correlation、decay_linear、rank、ts_rank、vwap；窗口 ts_rank=15.6948、ts_rank=4.4388、decay_linear=4.20501、decay_linear=16.4662、correlation=18.0175、ts_rank=3.43976、ts_rank=12.0647、adv=180；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：多层衰减流动性信号；核心算子：decay_linear, correlation, rank, close, adv。
- 源码计算片段：first = _ts_rank( _decay_linear( _correlation( _ts_rank(library.close, 3.43976), _ts_rank(_adv(library, 180), 12.0647), 18.0175, ), 4.20501, ), 15.6948, ) second = _ts_rank( _decay_linear( _rank(library.low + library.open - 2.0 * _vwap(library)) ** 2, 16.4662, ), 4.4388, ) return np.maximum(first, second)
- 本类中的具体角色：文章来源把它概括为“多层衰减流动性信号”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、low、open 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、low、open；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；文章分类表标记 IndNeut，但当前源码局部未检测到对应调用，需人工复核
- 索引说明：WorldQuant Formulaic Alpha #071。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha071 / 第 845-864 行；总览匹配行 8359、9525
- 与因子库总览一致性：mentioned
- 语义置信度：中：文章分类与当前实现标记存在差异

### alpha072
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、low、volume、平均成交额/成交量、滚动相关性、线性衰减、动态生成、字段回退
- 计算结构：字段 high、low、volume；算子 adv、correlation、decay_linear、rank、ts_rank、vwap；窗口 decay_linear=10.1519、decay_linear=2.95011、correlation=8.93345、correlation=6.86671、adv=40、ts_rank=3.72469、ts_rank=18.5188；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：衰减量价排名相关；核心算子：rank, correlation, vwap, adv, decay_linear。
- 源码计算片段：numerator = _rank( _decay_linear( _correlation((library.high + library.low) / 2.0, _adv(library, 40), 8.93345), 10.1519, ) ) denominator = _rank( _decay_linear( _correlation( _ts_rank(_vwap(library), 3.72469), _ts_rank(library.volume, 18.5188), 6.86671, ), 2.95011, ) ) return _safe_divide(numerator, denominator)
- 本类中的具体角色：文章来源把它概括为“衰减量价排名相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 high、low、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 high、low、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；文章分类表标记 IndNeut，但当前源码局部未检测到对应调用，需人工复核
- 索引说明：WorldQuant Formulaic Alpha #072。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha072 / 第 867-884 行；总览匹配行 9555
- 与因子库总览一致性：mentioned
- 语义置信度：中：文章分类与当前实现标记存在差异

### alpha075
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：low、volume、平均成交额/成交量、滚动相关性、截面排名、成交量加权价格、动态生成、字段回退
- 计算结构：字段 low、volume；算子 adv、correlation、rank、vwap；窗口 correlation=4.24304、correlation=12.4413、adv=50；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：vwap 与成交量排名的相关性；核心算子：rank, correlation, vwap, volume。
- 源码计算片段：left = _rank(_correlation(_vwap(library), library.volume, 4.24304)) right = _rank( _correlation(_rank(library.low), _rank(_adv(library, 50)), 12.4413) ) return _bool_signal(left < right)
- 本类中的具体角色：文章来源把它概括为“vwap 与成交量排名的相关性”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 low、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 low、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #075。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha075 / 第 913-918 行；总览匹配行 9625
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha076
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：low、平均成交额/成交量、滚动相关性、线性衰减、窗口差分、行业/分组中性化、行业中性化、动态生成
- 计算结构：字段 low；算子 adv、correlation、decay_linear、delta、indneutralize、rank、ts_rank、vwap；窗口 ts_rank=19.383、decay_linear=11.8259、decay_linear=17.1543、delta=1.24383、ts_rank=19.569、correlation=8.14941、adv=81；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：衰减 vwap 排名相关；核心算子：rank, decay_linear, correlation, vwap。
- 源码计算片段：first = _rank(_decay_linear(_delta(_vwap(library), 1.24383), 11.8259)) second = _ts_rank( _decay_linear( _ts_rank( _correlation( _indneutralize(library, library.low, "sector"), _adv(library, 81), 8.14941, ), 19.569, ), 17.1543, ), 19.383, ) return -np.maximum(first, second)
- 本类中的具体角色：文章来源把它概括为“衰减 vwap 排名相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 low 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 low；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #076。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha076 / 第 921-937 行；总览匹配行 9641
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha079
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、open、平均成交额/成交量、滚动相关性、窗口差分、行业/分组中性化、行业中性化、动态生成
- 计算结构：字段 close、open；算子 adv、correlation、delta、indneutralize、rank、ts_rank、vwap；窗口 delta=1.23438、correlation=14.6644、ts_rank=3.60973、ts_rank=9.18637、adv=150；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：行业中性 vwap 变化排名；核心算子：rank, delta, vwap, correlation, close。
- 源码计算片段：first = _indneutralize( library, library.close * 0.60733 + library.open * (1 - 0.60733), "sector", ) left = _rank(_delta(first, 1.23438)) right = _rank( _correlation( _ts_rank(_vwap(library), 3.60973), _ts_rank(_adv(library, 150), 9.18637), 14.6644, ) ) return _bool_signal(left < right)
- 本类中的具体角色：文章来源把它概括为“行业中性 vwap 变化排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、open 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、open；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #079。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha079 / 第 972-986 行；总览匹配行 9716
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha080
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、open、平均成交额/成交量、滚动相关性、窗口差分、行业/分组中性化、行业中性化、动态生成
- 计算结构：字段 high、open；算子 adv、correlation、delta、indneutralize、rank、sign、signed_power、ts_rank；窗口 ts_rank=5.53756、correlation=5.11456、delta=4.04545、adv=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：行业中性变化与量价相关；核心算子：rank, delta, close, correlation, adv。
- 源码计算片段：first = _indneutralize( library, library.open * 0.868128 + library.high * (1 - 0.868128), "industry", ) base = _rank(np.sign(_delta(first, 4.04545))) exponent = _ts_rank(_correlation(library.high, _adv(library, 10), 5.11456), 5.53756) return -_signed_power(base, exponent)
- 本类中的具体角色：文章来源把它概括为“行业中性变化与量价相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 high、open 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 high、open；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #080。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha080 / 第 989-997 行；总览匹配行 8359、9741
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha082
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：open、volume、滚动相关性、线性衰减、窗口差分、行业/分组中性化、行业中性化、动态生成
- 计算结构：字段 open、volume；算子 correlation、decay_linear、delta、indneutralize、rank、ts_rank；窗口 ts_rank=13.4283、decay_linear=14.8717、decay_linear=6.92131、delta=1.46063、correlation=17.4842；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：行业中性开盘变化排名；核心算子：rank, delta, open, correlation, adv。
- 源码计算片段：first = _rank(_decay_linear(_delta(library.open, 1.46063), 14.8717)) second = _ts_rank( _decay_linear( _correlation( _indneutralize(library, library.volume, "sector"), library.open * 0.634196 + library.open * (1 - 0.634196), 17.4842, ), 6.92131, ), 13.4283, ) return -np.minimum(first, second)
- 本类中的具体角色：文章来源把它概括为“行业中性开盘变化排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 open、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 open、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #082。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha082 / 第 1010-1023 行；总览匹配行 9778
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha087
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、abs、平均成交额/成交量、滚动相关性、线性衰减、窗口差分、行业中性化、动态生成
- 计算结构：字段 close；算子 abs、adv、correlation、decay_linear、delta、indneutralize、rank、ts_rank、vwap；窗口 ts_rank=14.4535、decay_linear=2.65461、decay_linear=4.89768、delta=1.91233、correlation=13.4132、adv=81；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：衰减 vwap 动量；核心算子：rank, decay_linear, delta, vwap, adv。
- 源码计算片段：vwap = _vwap(library) first = _rank( _decay_linear( _delta(library.close * 0.369701 + vwap * (1 - 0.369701), 1.91233), 2.65461, ) ) second = _ts_rank( _decay_linear( _correlation( _indneutralize(library, _adv(library, 81), "industry"), library.close, 13.4132, ).abs(), 4.89768, ), 14.4535, ) return -np.maximum(first, second)
- 本类中的具体角色：文章来源把它概括为“衰减 vwap 动量”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #087。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha087 / 第 1072-1091 行；总览匹配行 9880
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha089
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：low、平均成交额/成交量、滚动相关性、线性衰减、窗口差分、行业/分组中性化、行业中性化、动态生成
- 计算结构：字段 low；算子 adv、correlation、decay_linear、delta、indneutralize、ts_rank、vwap；窗口 ts_rank=3.79744、ts_rank=15.3012、decay_linear=5.51607、decay_linear=10.1466、correlation=6.94279、delta=3.48158、adv=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：衰减相关性信号；核心算子：decay_linear, correlation, rank。
- 源码计算片段：vwap = _vwap(library) first = _ts_rank( _decay_linear( _correlation( library.low * 0.967285 + library.low * (1 - 0.967285), _adv(library, 10), 6.94279, ), 5.51607, ), 3.79744, ) second = _ts_rank( _decay_linear( _delta(_indneutralize(library, vwap, "industry"), 3.48158), 10.1466, ), 15.3012, ) return first - second
- 本类中的具体角色：文章来源把它概括为“衰减相关性信号”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 low 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 low；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #089。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha089 / 第 1115-1135 行；总览匹配行 9939
- 与因子库总览一致性：mentioned
- 语义置信度：中：文章分类与当前实现标记存在差异

### alpha091
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、volume、平均成交额/成交量、滚动相关性、线性衰减、行业/分组中性化、行业中性化、动态生成
- 计算结构：字段 close、volume；算子 adv、correlation、decay_linear、indneutralize、rank、ts_rank、vwap；窗口 ts_rank=4.8667、decay_linear=3.83219、decay_linear=2.6809、decay_linear=16.398、correlation=4.01303、correlation=9.74928、adv=30；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：收盘-均量衰减相关；核心算子：rank, correlation, close, adv, decay_linear。
- 源码计算片段：first = _ts_rank( _decay_linear( _decay_linear( _correlation( _indneutralize(library, library.close, "industry"), library.volume, 9.74928, ), 16.398, ), 3.83219, ), 4.8667, ) second = _rank(_decay_linear(_correlation(_vwap(library), _adv(library, 30), 4.01303), 2.6809)) return -(first - second)
- 本类中的具体角色：文章来源把它概括为“收盘-均量衰减相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #091。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha091 / 第 1150-1166 行；总览匹配行 8361、9990
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha093
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、平均成交额/成交量、滚动相关性、线性衰减、窗口差分、行业/分组中性化、行业中性化、动态生成
- 计算结构：字段 close；算子 adv、correlation、decay_linear、delta、indneutralize、rank、ts_rank、vwap；窗口 ts_rank=7.54455、decay_linear=19.848、decay_linear=16.2664、correlation=17.4193、delta=2.77377、adv=81；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：行业中性衰减 vwap 相关；核心算子：rank, correlation, vwap, adv, decay_linear。
- 源码计算片段：first = _ts_rank( _decay_linear( _correlation( _indneutralize(library, _vwap(library), "industry"), _adv(library, 81), 17.4193, ), 19.848, ), 7.54455, ) second = _rank( _decay_linear( _delta( library.close * 0.524434 + _vwap(library) * (1 - 0.524434), 2.77377, ), 16.2664, ) ) return _safe_divide(first, second)
- 本类中的具体角色：文章来源把它概括为“行业中性衰减 vwap 相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #093。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha093 / 第 1184-1205 行；总览匹配行 10040
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha097
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：low、平均成交额/成交量、滚动相关性、线性衰减、窗口差分、行业/分组中性化、行业中性化、动态生成
- 计算结构：字段 low；算子 adv、correlation、decay_linear、delta、indneutralize、rank、ts_rank、vwap；窗口 ts_rank=6.71659、decay_linear=20.4523、decay_linear=15.7152、delta=3.3705、ts_rank=18.5925、correlation=4.97547、ts_rank=7.87871、ts_rank=17.255、adv=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：行业中性衰减流动性；核心算子：rank, decay_linear, delta, correlation, adv。
- 源码计算片段：vwap = _vwap(library) first = _rank( _decay_linear( _delta( _indneutralize( library, library.low * 0.721001 + vwap * (1 - 0.721001), "industry", ), 3.3705, ), 20.4523, ) ) second = _ts_rank( _decay_linear( _ts_rank( _correlation( _ts_rank(library.low, 7.87871), _ts_rank(_adv(library, 60), 17.255), 4.97547, ), 18.5925, ), 15.7152, ), 6.71659, ) return -(first - second)
- 本类中的具体角色：文章来源把它概括为“行业中性衰减流动性”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 low 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 low；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #097。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha097 / 第 1262-1291 行；总览匹配行 10150
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha100
- 主分类：流动性与复合
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、volume、平均成交额/成交量、滚动相关性、行业中性化、动态生成
- 计算结构：字段 close、high、low、volume；算子 adv、correlation、indneutralize、rank、scale、ts_argmin；窗口 adv=20、correlation=5、ts_argmin=30；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：波动率与流动性的相关排名；核心算子：rank, stddev, correlation, adv。
- 源码计算片段：inner = _safe_divide( ((library.close - library.low) - (library.high - library.close)) * library.volume, library.high - library.low, ) first = _scale( _indneutralize( library, _indneutralize(library, _rank(inner), "subindustry"), "subindustry", ) ) second = _scale( _indneutralize( library, _correlation(library.close, _rank(_adv(library, 20)), 5) - _rank(_ts_argmin(library.close, 30)), "subindustry", ) ) return -(1.5 * first - second) * _safe_divide( library.volume, _adv(library, 20) )
- 本类中的具体角色：文章来源把它概括为“波动率与流动性的相关排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、high、low、volume 的活跃度、成交确认和价格变化组合起来，观察资金参与度或量价联动；复合结构越深，越需要拆开验证每一层的经济含义。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于成交活跃度、资金确认和复合量价关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；源码包含行业/分组中性化或相关字段，需核对行业分类版本；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #100。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha100 / 第 1333-1355 行；总览匹配行 8361、10245
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

## 日内结构

> 因子数量：113；来源分布：gtja_alpha191 60、technical_lib 20、classic_indicators 12、worldquant_alpha101 12、alpha_features 9

开盘、收盘、最高、最低和 VWAP 的同日相对关系，反映日内价格路径和成交位置。它回答的是“今天这根 K 线如何走完”，不是单纯的长期收益问题。 收盘靠近最高价可能表示日内买方占优，收盘低于 VWAP 可能表示高位成交后回落；这些是行为解释假设，需要结合信号生成时点和持有周期。

常见表达是 close-open、close/high/low 的位置比值、high-low 振幅、VWAP-close 偏离，以及 sqrt(high*low)-VWAP 等同日结构。 Alpha#101 的 (close-open)/(high-low+0.001) 是 close location value 风格的日内收益/振幅比；Alpha#42 通过 VWAP 与 close 的排名偏离描述收盘回落。方向由分子、分母和外层 rank/sign 共同决定。

Alpha#101 值接近正一表示开盘到收盘接近日内单边上行，接近零表示日内振幅较大但收盘接近开盘；Alpha#42 关注 VWAP 高于收盘时的日内回落结构。

边界上，这类因子通常使用当日 OHLC/VWAP。Alpha#42 等没有历史滞后、依赖当日数据的结构，在 A 股 T+1 约束下不能直接等同于可执行的隔夜信号；需要明确收盘后生成、次日执行还是盘中使用。

### alpha158_klen
- 主分类：日内结构
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、high、low、动态生成
- 计算结构：字段 open、high、low；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha158 KLEN。 该因子来自共享模板，具体参数为 feature=klen。
- 源码计算片段：共享模板具体公式：(high - low) / open
- 本类中的具体角色：它是共享模板的具体参数实例（feature=klen）；同一公式族中的差异主要来自字段、窗口或日偏移，参数变化会改变观察周期和输入相对位置。
- 经济直觉：利用 open、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 open、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：Alpha158 KLEN。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6753、6759
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha158_klow
- 主分类：日内结构
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、low、close、逐点最大值、逐点最小值、动态生成
- 计算结构：字段 open、low、close；算子 maximum、minimum；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha158 KLOW。 该因子来自共享模板，具体参数为 feature=klow。
- 源码计算片段：共享模板具体公式：(minimum(open, close) - low) / open
- 本类中的具体角色：它是共享模板的具体参数实例（feature=klow）；同一公式族中的差异主要来自字段、窗口或日偏移，参数变化会改变观察周期和输入相对位置。
- 经济直觉：利用 open、low、close 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 open、low、close；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：Alpha158 KLOW。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6793、6799
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha158_kmid
- 主分类：日内结构
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、动态生成
- 计算结构：字段 open、close；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha158 KMID。 该因子来自共享模板，具体参数为 feature=kmid。
- 源码计算片段：共享模板具体公式：(close - open) / open
- 本类中的具体角色：它是共享模板的具体参数实例（feature=kmid）；同一公式族中的差异主要来自字段、窗口或日偏移，参数变化会改变观察周期和输入相对位置。
- 经济直觉：利用 open、close 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 open、close；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：Alpha158 KMID。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6743、6749
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha158_ksft
- 主分类：日内结构
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、high、low、close、动态生成
- 计算结构：字段 open、high、low、close；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha158 KSFT。 该因子来自共享模板，具体参数为 feature=ksft。
- 源码计算片段：共享模板具体公式：(2 * close - high - low) / open
- 本类中的具体角色：它是共享模板的具体参数实例（feature=ksft）；同一公式族中的差异主要来自字段、窗口或日偏移，参数变化会改变观察周期和输入相对位置。
- 经济直觉：利用 open、high、low、close 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 open、high、low、close；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：Alpha158 KSFT。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6813、6819
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha158_kup
- 主分类：日内结构
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、high、close、逐点最大值、逐点最小值、动态生成
- 计算结构：字段 open、high、close；算子 maximum、minimum；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha158 KUP。 该因子来自共享模板，具体参数为 feature=kup。
- 源码计算片段：共享模板具体公式：(high - maximum(open, close)) / open
- 本类中的具体角色：它是共享模板的具体参数实例（feature=kup）；同一公式族中的差异主要来自字段、窗口或日偏移，参数变化会改变观察周期和输入相对位置。
- 经济直觉：利用 open、high、close 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 open、high、close；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：Alpha158 KUP。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6773、6779
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha360_high0
- 主分类：日内结构
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：high、close、历史位移、动态生成
- 计算结构：字段 high、close；算子 shift；窗口 shift=0；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha360 HIGH0。 该因子来自共享模板，具体参数为 field=high、day=0。
- 源码计算片段：共享模板具体公式：high.shift(0) / close
- 本类中的具体角色：它是共享模板的具体参数实例（field=high、day=0）；同一公式族中的差异主要来自字段、窗口或日偏移，参数变化会改变观察周期和输入相对位置。
- 经济直觉：利用 high、close 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、close；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：Alpha360 HIGH0。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4341、4347
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha360_low0
- 主分类：日内结构
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：low、close、历史位移、动态生成
- 计算结构：字段 low、close；算子 shift；窗口 shift=0；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha360 LOW0。 该因子来自共享模板，具体参数为 field=low、day=0。
- 源码计算片段：共享模板具体公式：low.shift(0) / close
- 本类中的具体角色：它是共享模板的具体参数实例（field=low、day=0）；同一公式族中的差异主要来自字段、窗口或日偏移，参数变化会改变观察周期和输入相对位置。
- 经济直觉：利用 low、close 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 low、close；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：Alpha360 LOW0。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 4941、4947
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha360_open0
- 主分类：日内结构
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：open、close、历史位移、动态生成
- 计算结构：字段 open、close；算子 shift；窗口 shift=0；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha360 OPEN0。 该因子来自共享模板，具体参数为 field=open、day=0。
- 源码计算片段：共享模板具体公式：open.shift(0) / close
- 本类中的具体角色：它是共享模板的具体参数实例（field=open、day=0）；同一公式族中的差异主要来自字段、窗口或日偏移，参数变化会改变观察周期和输入相对位置。
- 经济直觉：利用 open、close 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 open、close；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：Alpha360 OPEN0。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 3741、3747
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha360_vwap0
- 主分类：日内结构
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：vwap、close、历史位移、成交量加权价格、动态生成、字段回退
- 计算结构：字段 vwap、close；算子 shift、vwap；窗口 shift=0；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引名称说明：Alpha360 VWAP0。 该因子来自共享模板，具体参数为 field=vwap、day=0。
- 源码计算片段：共享模板具体公式：vwap.shift(0) / close
- 本类中的具体角色：它是共享模板的具体参数实例（field=vwap、day=0）；同一公式族中的差异主要来自字段、窗口或日偏移，参数变化会改变观察周期和输入相对位置。
- 经济直觉：利用 vwap、close 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 vwap、close；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：Alpha360 VWAP0。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha360_factors / 第 64-87 行；总览匹配行 5541、5547
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### adtm
- 主分类：日内结构
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：high、low、open、滚动窗口、历史位移、求和
- 计算结构：字段 high、low、open；算子 rolling、shift、sum、where；窗口 window=23；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：动态买卖气指标。
- 源码计算片段："""动态买卖气指标。""" previous = self.open.shift() dtm = pd_concat_max(self.high - self.open, self.open - previous).where(self.open > previous, 0.0) dbm = (self.open - self.low).where(self.open < previous, 0.0) stm, sbm = dtm.rolling(window).sum(), dbm.rolling(window).sum() return ((stm - sbm) / stm.where(stm > sbm, sbm)).where((stm != 0) | (sbm != 0), 0.0)
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low、open 的滚动窗口、历史位移、求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：动态买卖气指标。
- 来源证据：Factor/libraries/classic_indicators.py / adtm / 第 221-227 行；总览匹配行 607
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### cci
- 主分类：日内结构
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、high、low、abs、apply、均值
- 计算结构：字段 close、high、low；算子 abs、apply、mean、rolling；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：顺势指标。
- 源码计算片段："""顺势指标。""" typical = (self.high + self.low + self.close) / 3 average = typical.rolling(window).mean() deviation = typical.rolling(window).apply(lambda values: np.mean(np.abs(values - values.mean())), raw=True) return (typical - average) / (0.015 * deviation)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的abs、apply、均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：顺势指标。
- 来源证据：Factor/libraries/classic_indicators.py / cci / 第 94-99 行；总览匹配行 613、936、943
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### cdp
- 主分类：日内结构
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、high、low
- 计算结构：字段 close、high、low；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：逆势操作指标中枢 CDP。
- 源码计算片段："""逆势操作指标中枢 CDP。""" return (self.high + self.low + self.close) / 3
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点
- 索引说明：逆势操作指标中枢 CDP。
- 来源证据：Factor/libraries/classic_indicators.py / cdp / 第 195-197 行；总览匹配行 614
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### cr
- 主分类：日内结构
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、high、low、滚动窗口、历史位移、求和
- 计算结构：字段 close、high、low；算子 rolling、shift、sum；窗口 window=26；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：能量指标。
- 源码计算片段："""能量指标。""" middle = (self.high.shift() + self.low.shift() + self.close.shift()) / 3 return (self.high - middle).rolling(window).sum() / (middle - self.low).rolling(window).sum() * 100
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动窗口、历史位移、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：能量指标。
- 来源证据：Factor/libraries/classic_indicators.py / cr / 第 146-149 行；总览匹配行 615
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### cvlt
- 主分类：日内结构
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：high、low、ewm、均值、历史位移
- 计算结构：字段 high、low；算子 ewm、mean、shift；窗口 window=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：佳庆离散指标。
- 源码计算片段："""佳庆离散指标。""" ema = (self.high - self.low).ewm(span=window, adjust=False).mean() return (ema - ema.shift(window)) / ema.shift(window)
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的ewm、均值、历史位移实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点
- 索引说明：佳庆离散指标。
- 来源证据：Factor/libraries/classic_indicators.py / cvlt / 第 292-295 行；总览匹配行 616
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### donchian_position
- 主分类：日内结构
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、high、low、滚动最大值、滚动最小值、滚动窗口
- 计算结构：字段 close、high、low；算子 max、min、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：唐奇安通道位置：收盘价在近期高低区间中的归一化位置。
- 源码计算片段："""唐奇安通道位置：收盘价在近期高低区间中的归一化位置。""" upper = self.high.rolling(window).max() lower = self.low.rolling(window).min() return (self.close - lower) / (upper - lower + 1e-10)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动最大值、滚动最小值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：唐奇安通道位置：收盘价在近期高低区间中的归一化位置。
- 来源证据：Factor/libraries/classic_indicators.py / donchian_position / 第 246-250 行；总览匹配行 620
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### donchian_width
- 主分类：日内结构
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、high、low、abs、滚动最大值、滚动最小值
- 计算结构：字段 close、high、low；算子 abs、max、min、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：唐奇安通道宽度：近期高低区间相对收盘价的幅度。
- 源码计算片段："""唐奇安通道宽度：近期高低区间相对收盘价的幅度。""" upper = self.high.rolling(window).max() lower = self.low.rolling(window).min() return (upper - lower) / (self.close.abs() + 1e-10)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的abs、滚动最大值、滚动最小值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：唐奇安通道宽度：近期高低区间相对收盘价的幅度。
- 来源证据：Factor/libraries/classic_indicators.py / donchian_width / 第 252-256 行；总览匹配行 621
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### kdj
- 主分类：日内结构
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、high、low、滚动最大值、滚动最小值、滚动窗口
- 计算结构：字段 close、high、low；算子 max、min、rolling；窗口 window=9；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：随机指标主线 J。
- 源码计算片段："""随机指标主线 J。""" high, low = self.high.rolling(window).max(), self.low.rolling(window).min() rsv = (self.close - low) / (high - low) * 100 k = self._sma(rsv, k_window) d = self._sma(k, d_window) return 3 * k - 2 * d
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动最大值、滚动最小值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：随机指标主线 J。
- 来源证据：Factor/libraries/classic_indicators.py / kdj / 第 111-117 行；总览匹配行 625
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### mass
- 主分类：日内结构
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：high、low、均值、滚动窗口、求和
- 计算结构：字段 high、low；算子 mean、rolling、sum；窗口 short=9、long=25；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：梅丝线。
- 源码计算片段："""梅丝线。""" first = (self.high - self.low).rolling(short).mean() return (first / first.rolling(short).mean()).rolling(long).sum()
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的均值、滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：梅丝线。
- 来源证据：Factor/libraries/classic_indicators.py / mass / 第 278-281 行；总览匹配行 630
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### wad
- 主分类：日内结构
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、high、low、历史位移、where
- 计算结构：字段 close、high、low；算子 shift、where；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：威廉聚散指标。
- 源码计算片段："""威廉聚散指标。""" previous = self.close.shift() low = pd_concat_min(previous, self.low) high = pd_concat_max(previous, self.high) daily = (self.close - low).where(self.close > previous, (self.close - high).where(self.close < previous, 0.0)) return daily.cumsum()
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的历史位移、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点
- 索引说明：威廉聚散指标。
- 来源证据：Factor/libraries/classic_indicators.py / wad / 第 163-169 行；总览匹配行 651
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### wr
- 主分类：日内结构
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、high、low、滚动最大值、滚动最小值、滚动窗口
- 计算结构：字段 close、high、low；算子 max、min、rolling；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：威廉指标。
- 源码计算片段："""威廉指标。""" highest, lowest = self.high.rolling(window).max(), self.low.rolling(window).min() return (highest - self.close) / (highest - lowest) * 100
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动最大值、滚动最小值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：威廉指标。
- 来源证据：Factor/libraries/classic_indicators.py / wr / 第 141-144 行；总览匹配行 652
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### wvad
- 主分类：日内结构
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、high、low、open、volume、滚动窗口
- 计算结构：字段 close、high、low、open、volume；算子 rolling、sum；窗口 window=24；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：威廉变异离散量。
- 源码计算片段："""威廉变异离散量。""" return ((self.close - self.open) / (self.high - self.low) * self.volume).rolling(window).sum()
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、open、volume 的滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、open、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、open、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：威廉变异离散量。
- 来源证据：Factor/libraries/classic_indicators.py / wvad / 第 183-185 行；总览匹配行 653、3111、3119
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### alpha191_002
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、窗口差分、动态生成
- 计算结构：字段 close、high、low；算子 delta；窗口 delta=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #002。
- 源码计算片段：numerator = (lib.close - lib.low) - (lib.high - lib.close) return -_delta(_safe_divide(numerator, lib.high - lib.low), 1)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的窗口差分实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #002。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha002 / 第 376-378 行；总览匹配行 10310、10336
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_003
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 close、high、low；算子 delay、ts_sum、where；窗口 delay=1、ts_sum=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #003。
- 源码计算片段：previous = _delay(lib.close, 1) up = lib.close > previous down = lib.close < previous part_up = lib.close - _elementwise_min(lib.low, previous) part_down = lib.close - _elementwise_max(lib.high, previous) part = part_up.where(up, part_down.where(down, 0.0)) return _ts_sum(part, 6)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #003。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha003 / 第 381-388 行；总览匹配行 10349
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_006
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、open、窗口差分、截面排名、sign、动态生成
- 计算结构：字段 high、open；算子 delta、rank、sign；窗口 delta=4；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #006。
- 源码计算片段：return -_rank(np.sign(_delta(lib.open * 0.85 + lib.high * 0.15, 4)))
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、open 的窗口差分、截面排名、sign实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #006。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha006 / 第 409-410 行；总览匹配行 10401
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_008
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、窗口差分、截面排名、成交量加权价格、动态生成、字段回退
- 计算结构：字段 high、low；算子 delta、rank、vwap；窗口 delta=4；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #008。
- 源码计算片段：weighted = (lib.high + lib.low) / 2.0 * 0.2 + lib._vwap() * 0.8 return _rank(-_delta(weighted, 4))
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的窗口差分、截面排名、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #008。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha008 / 第 418-420 行；总览匹配行 10426
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_009
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、volume、历史滞后、动态生成
- 计算结构：字段 high、low、volume；算子 delay；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #009。
- 源码计算片段：midpoint_change = (lib.high + lib.low) / 2.0 - (_delay(lib.high, 1) + _delay(lib.low, 1)) / 2.0 return _sma(_safe_divide(midpoint_change * (lib.high - lib.low), lib.volume), 7, 2)
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low、volume 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #009。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha009 / 第 423-425 行；总览匹配行 10310、10439
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_011
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、volume、滚动求和、动态生成
- 计算结构：字段 close、high、low、volume；算子 ts_sum；窗口 ts_sum=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #011。
- 源码计算片段：return _ts_sum(_safe_divide((2 * lib.close - lib.low - lib.high) * lib.volume, lib.high - lib.low), 6)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、volume 的滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #011。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha011 / 第 434-435 行；总览匹配行 10311、10466
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_012
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、open、abs、截面排名、滚动求和、成交量加权价格、动态生成、字段回退
- 计算结构：字段 close、open；算子 abs、rank、ts_sum、vwap；窗口 ts_sum=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #012。
- 源码计算片段：return _rank(lib.open - _ts_sum(lib._vwap(), 10) / 10.0) * _rank((lib.close - lib._vwap()).abs())
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、open 的abs、截面排名、滚动求和、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #012。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha012 / 第 438-439 行；总览匹配行 10478
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_013
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、sqrt、成交量加权价格、动态生成、字段回退
- 计算结构：字段 high、low；算子 sqrt、vwap；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #013。
- 源码计算片段：return np.sqrt(lib.high * lib.low) - lib._vwap()
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的sqrt、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #013。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha013 / 第 442-443 行；总览匹配行 10490
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_015
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、open、历史滞后、动态生成
- 计算结构：字段 close、open；算子 delay；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #015。
- 源码计算片段：return _safe_divide(lib.open, _delay(lib.close, 1)) - 1.0
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、open 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #015。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha015 / 第 450-451 行；总览匹配行 10514
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_028
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、滚动最大值、滚动最小值、动态生成
- 计算结构：字段 close、high、low；算子 ts_max、ts_min；窗口 ts_min=9、ts_max=9；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #028。
- 源码计算片段：lower = _ts_min(lib.low, 9) spread = _ts_max(lib.high, 9) - lower kd = _safe_divide(lib.close - lower, spread) * 100.0 smooth = _sma(kd, 3, 1) return 3.0 * smooth - 2.0 * _sma(smooth, 3, 1)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动最大值、滚动最小值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #028。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha028 / 第 513-518 行；总览匹配行 10681
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_033
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：low、volume、历史滞后、截面排名、收益序列、滚动最小值、动态生成
- 计算结构：字段 low、volume；算子 delay、rank、returns、ts_min、ts_rank、ts_sum；窗口 ts_min=5、ts_rank=5、delay=5、ts_sum=240、ts_sum=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #033。
- 源码计算片段：low5 = _ts_min(lib.low, 5) return (-low5 + _delay(low5, 5)) * _rank((_ts_sum(lib._returns(), 240) - _ts_sum(lib._returns(), 20)) / 220.0) * _ts_rank(lib.volume, 5)
- 本类中的具体角色：它在“日内结构”总论中具体通过 low、volume 的历史滞后、截面排名、收益序列、滚动最小值、时间序列排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 low、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 low、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #033。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha033 / 第 539-541 行；总览匹配行 10747
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_037
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：open、历史滞后、截面排名、收益序列、滚动求和、动态生成
- 计算结构：字段 open；算子 delay、rank、returns、ts_sum；窗口 ts_sum=5、delay=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #037。
- 源码计算片段：inner = _ts_sum(lib.open, 5) * _ts_sum(lib._returns(), 5) return -_rank(inner - _delay(inner, 10))
- 本类中的具体角色：它在“日内结构”总论中具体通过 open 的历史滞后、截面排名、收益序列、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #037。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha037 / 第 558-560 行；总览匹配行 10798
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_038
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、窗口差分、滚动均值、where、动态生成
- 计算结构：字段 high；算子 delta、ts_mean、where；窗口 ts_mean=20、delta=2；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #038。
- 源码计算片段：return (-_delta(lib.high, 2)).where(_ts_mean(lib.high, 20) < lib.high, 0.0)
- 本类中的具体角色：它在“日内结构”总论中具体通过 high 的窗口差分、滚动均值、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #038。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha038 / 第 563-564 行；总览匹配行 10811
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_047
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、滚动最大值、滚动最小值、动态生成
- 计算结构：字段 close、high、low；算子 ts_max、ts_min；窗口 ts_max=6、ts_min=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #047。
- 源码计算片段：spread = _ts_max(lib.high, 6) - _ts_min(lib.low, 6) return _sma(_safe_divide(_ts_max(lib.high, 6) - lib.close, spread) * 100.0, 9, 1)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动最大值、滚动最小值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #047。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha047 / 第 605-607 行；总览匹配行 10925
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_049
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 high、low；算子 delay、ts_sum、where；窗口 delay=1、ts_sum=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #049。
- 源码计算片段：previous_sum = _delay(lib.high, 1) + _delay(lib.low, 1) current_sum = lib.high + lib.low movement = _tr_parts(lib) down = movement.where(current_sum < previous_sum, 0.0) up = movement.where(current_sum > previous_sum, 0.0) return _safe_divide(_ts_sum(down, 12), _ts_sum(down, 12) + _ts_sum(up, 12))
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #049。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha049 / 第 619-625 行；总览匹配行 10955
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_050
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 high、low；算子 delay、ts_sum、where；窗口 delay=1、ts_sum=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #050。
- 源码计算片段：previous_sum = _delay(lib.high, 1) + _delay(lib.low, 1) current_sum = lib.high + lib.low movement = _tr_parts(lib) up = movement.where(current_sum > previous_sum, 0.0) down = movement.where(current_sum < previous_sum, 0.0) return _safe_divide(_ts_sum(up, 12) - _ts_sum(down, 12), _ts_sum(up, 12) + _ts_sum(down, 12))
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #050。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha050 / 第 628-634 行；总览匹配行 10972
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_051
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 high、low；算子 delay、ts_sum、where；窗口 delay=1、ts_sum=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #051。
- 源码计算片段：previous_sum = _delay(lib.high, 1) + _delay(lib.low, 1) current_sum = lib.high + lib.low movement = _tr_parts(lib) up = movement.where(current_sum > previous_sum, 0.0) down = movement.where(current_sum < previous_sum, 0.0) return _safe_divide(_ts_sum(up, 12), _ts_sum(up, 12) + _ts_sum(down, 12))
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #051。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha051 / 第 637-643 行；总览匹配行 10989
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_052
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、历史滞后、滚动求和、动态生成
- 计算结构：字段 close、high、low；算子 delay、ts_sum；窗口 ts_sum=26、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #052。
- 源码计算片段：typical = (lib.high + lib.low + lib.close) / 3.0 return _safe_divide(_ts_sum(_elementwise_max(lib.high - _delay(typical, 1), 0.0), 26), _ts_sum(_elementwise_max(_delay(typical, 1) - lib.low, 0.0), 26)) * 100.0
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的历史滞后、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #052。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha052 / 第 646-648 行；总览匹配行 11006
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_054
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、open、abs、滚动相关性、截面排名、滚动波动率、动态生成
- 计算结构：字段 close、open；算子 abs、corr、rank、ts_std；窗口 ts_std=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #054。
- 源码计算片段：return _rank(_ts_std((lib.close - lib.open).abs(), 5) + (lib.close - lib.open) + _corr(lib.close, lib.open, 10))
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、open 的abs、滚动相关性、截面排名、滚动波动率实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #054。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha054 / 第 655-656 行；总览匹配行 11031
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_055
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、open、abs、历史滞后、动态生成
- 计算结构：字段 close、high、low、open；算子 abs、delay、ts_sum、where；窗口 delay=1、ts_sum=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #055。
- 源码计算片段：previous_close = _delay(lib.close, 1) previous_open = _delay(lib.open, 1) a = (lib.high - previous_close).abs() b = (lib.low - previous_close).abs() c = (lib.high - _delay(lib.low, 1)).abs() d = (previous_close - previous_open).abs() condition_a = (a > b) & (a > c) condition_b = (b > c) & (b > a) denominator = pd.DataFrame( np.where(condition_a, a + b / 2.0 + d / 4.0, np.where(condition_b, b + a / 2.0 + d / 4.0, c + d / 4.0)), index=lib.close.index, columns=lib.close.columns, ) part = 16.0 * (lib.close + (lib.clos…
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、open 的abs、历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #055。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha055 / 第 659-674 行；总览匹配行 11043
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_057
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、滚动最大值、滚动最小值、动态生成
- 计算结构：字段 close、high、low；算子 ts_max、ts_min；窗口 ts_max=9、ts_min=9；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #057。
- 源码计算片段：spread = _ts_max(lib.high, 9) - _ts_min(lib.low, 9) kd = _safe_divide(lib.close - _ts_min(lib.low, 9), spread) * 100.0 return _sma(kd, 3, 1)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动最大值、滚动最小值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #057。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha057 / 第 683-686 行；总览匹配行 11083
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_059
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 close、high、low；算子 delay、ts_sum、where；窗口 delay=1、ts_sum=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #059。
- 源码计算片段：previous = _delay(lib.close, 1) up = lib.close > previous down = lib.close < previous part = (lib.close - _elementwise_min(lib.low, previous)).where(up, (lib.close - _elementwise_max(lib.high, previous)).where(down, 0.0)) return _ts_sum(part, 20)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #059。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha059 / 第 693-698 行；总览匹配行 11109
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_060
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、volume、滚动求和、动态生成
- 计算结构：字段 close、high、low、volume；算子 ts_sum；窗口 ts_sum=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #060。
- 源码计算片段：return _ts_sum(_safe_divide(((lib.close - lib.low) - (lib.high - lib.close)) * lib.volume, lib.high - lib.low), 20)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、volume 的滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #060。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha060 / 第 701-702 行；总览匹配行 11125
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_068
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、volume、历史滞后、动态生成
- 计算结构：字段 high、low、volume；算子 delay；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #068。
- 源码计算片段：midpoint_change = (lib.high + lib.low) / 2.0 - (_delay(lib.high, 1) + _delay(lib.low, 1)) / 2.0 return _sma(_safe_divide(midpoint_change * (lib.high - lib.low), lib.volume), 15, 2) * 100.0
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low、volume 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #068。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha068 / 第 740-742 行；总览匹配行 11228
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_069
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、open、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 high、low、open；算子 delay、ts_sum、where；窗口 delay=1、ts_sum=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #069。
- 源码计算片段：previous_open = _delay(lib.open, 1) dtm = _elementwise_max(lib.high - lib.open, lib.open - previous_open).where(lib.open > previous_open, 0.0) dbm = _elementwise_max(lib.open - lib.low, lib.open - previous_open).where(lib.open < previous_open, 0.0) sdtm = _ts_sum(dtm, 20) sdbm = _ts_sum(dbm, 20) return _safe_divide(sdtm - sdbm, sdtm).where(sdtm > sdbm, _safe_divide(sdtm - sdbm, sdbm).where(sdtm < sdbm, 0.0))
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low、open 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #069。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha069 / 第 745-751 行；总览匹配行 11241
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_072
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、滚动最大值、滚动最小值、动态生成
- 计算结构：字段 close、high、low；算子 ts_max、ts_min；窗口 ts_max=6、ts_min=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #072。
- 源码计算片段：spread = _ts_max(lib.high, 6) - _ts_min(lib.low, 6) return _sma(_safe_divide(_ts_max(lib.high, 6) - lib.close, spread) * 100.0, 15, 1)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动最大值、滚动最小值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #072。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha072 / 第 763-765 行；总览匹配行 11283
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_075
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、open、动态生成
- 计算结构：字段 close、open；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #075。
- 源码计算片段：benchmark_close, benchmark_open = lib._benchmark() stock_up_benchmark_down = (lib.close > lib.open).mul(benchmark_close < benchmark_open, axis=0) benchmark_down = pd.DataFrame( np.broadcast_to((benchmark_close < benchmark_open).to_numpy()[:, None], lib.close.shape), index=lib.close.index, columns=lib.close.columns, ) return _safe_divide(_count(stock_up_benchmark_down, 50), _count(benchmark_down, 50))
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、open 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #075。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha075 / 第 780-788 行；总览匹配行 11324
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_078
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、abs、滚动均值、动态生成
- 计算结构：字段 close、high、low；算子 abs、ts_mean；窗口 ts_mean=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #078。
- 源码计算片段：typical = (lib.high + lib.low + lib.close) / 3.0 mean12 = _ts_mean(typical, 12) return _safe_divide(typical - mean12, _ts_mean((lib.close - mean12).abs(), 12) * 0.015)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的abs、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #078。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha078 / 第 802-805 行；总览匹配行 11370
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_082
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、滚动最大值、滚动最小值、动态生成
- 计算结构：字段 close、high、low；算子 ts_max、ts_min；窗口 ts_max=6、ts_min=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #082。
- 源码计算片段：spread = _ts_max(lib.high, 6) - _ts_min(lib.low, 6) return _sma(_safe_divide(_ts_max(lib.high, 6) - lib.close, spread) * 100.0, 20, 1)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动最大值、滚动最小值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #082。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha082 / 第 821-823 行；总览匹配行 11421
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_087
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、open、线性衰减、窗口差分、截面排名、动态生成、字段回退
- 计算结构：字段 high、low、open；算子 decay_linear、delta、rank、ts_rank、vwap；窗口 ts_rank=7、decay_linear=7、decay_linear=11、delta=4；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #087。
- 源码计算片段：first = _rank(_decay_linear(_delta(lib._vwap(), 4), 7)) second = _ts_rank(_decay_linear(_safe_divide(lib.high - lib._vwap(), lib.open - (lib.high + lib.low) / 2.0), 11), 7) return -(first + second)
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low、open 的线性衰减、窗口差分、截面排名、时间序列排名、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #087。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha087 / 第 845-848 行；总览匹配行 11485
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_093
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：low、open、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 low、open；算子 delay、ts_sum、where；窗口 delay=1、ts_sum=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #093。
- 源码计算片段：previous_open = _delay(lib.open, 1) part = _elementwise_max(lib.open - lib.low, lib.open - previous_open).where(lib.open < previous_open, 0.0) return _ts_sum(part, 20)
- 本类中的具体角色：它在“日内结构”总论中具体通过 low、open 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #093。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha093 / 第 876-879 行；总览匹配行 11564
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_096
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、滚动最大值、滚动最小值、动态生成
- 计算结构：字段 close、high、low；算子 ts_max、ts_min；窗口 ts_max=9、ts_min=9；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #096。
- 源码计算片段：spread = _ts_max(lib.high, 9) - _ts_min(lib.low, 9) kd = _safe_divide(lib.close - _ts_min(lib.low, 9), spread) * 100.0 return _sma(_sma(kd, 3, 1), 3, 1)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动最大值、滚动最小值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #096。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha096 / 第 892-895 行；总览匹配行 11604
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_103
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：low、动态生成
- 计算结构：字段 low；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #103。
- 源码计算片段：return (20.0 - _lowday(lib.low, 20)) / 20.0 * 100.0
- 本类中的具体角色：它在“日内结构”总论中具体通过 low 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #103。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha103 / 第 927-928 行；总览匹配行 11695
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_107
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、open、历史滞后、截面排名、动态生成
- 计算结构：字段 close、high、low、open；算子 delay、rank；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #107。
- 源码计算片段：return -_rank(lib.open - _delay(lib.high, 1)) * _rank(lib.open - _delay(lib.close, 1)) * _rank(lib.open - _delay(lib.low, 1))
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、open 的历史滞后、截面排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #107。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha107 / 第 943-944 行；总览匹配行 11743
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_109
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、动态生成
- 计算结构：字段 high、low；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #109。
- 源码计算片段：hl = lib.high - lib.low smooth = _sma(hl, 10, 2) return _safe_divide(smooth, _sma(smooth, 10, 2))
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #109。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha109 / 第 951-954 行；总览匹配行 11767
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_110
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、历史滞后、滚动求和、动态生成
- 计算结构：字段 close、high、low；算子 delay、ts_sum；窗口 delay=1、ts_sum=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #110。
- 源码计算片段：previous = _delay(lib.close, 1) return _safe_divide(_ts_sum(_elementwise_max(lib.high - previous, 0.0), 20), _ts_sum(_elementwise_max(previous - lib.low, 0.0), 20)) * 100.0
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的历史滞后、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #110。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha110 / 第 957-959 行；总览匹配行 11781
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_111
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、volume、动态生成
- 计算结构：字段 close、high、low、volume；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #111。
- 源码计算片段：value = _safe_divide(((lib.close - lib.low) - (lib.high - lib.close)) * lib.volume, lib.high - lib.low) return _sma(value, 11, 2) - _sma(value, 4, 2)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、volume 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #111。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha111 / 第 962-964 行；总览匹配行 11794
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_114
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、volume、历史滞后、截面排名、动态生成、字段回退
- 计算结构：字段 close、high、low、volume；算子 delay、rank、ts_mean、vwap；窗口 ts_mean=5、delay=2；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #114。
- 源码计算片段：mean5 = _ts_mean(lib.close, 5) hl5 = _safe_divide(lib.high - lib.low, mean5) return _safe_divide(_rank(_delay(hl5, 2)) * _rank(_rank(lib.volume)), _safe_divide(hl5, lib._vwap() - lib.close))
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、volume 的历史滞后、截面排名、滚动均值、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #114。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha114 / 第 980-983 行；总览匹配行 11836
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_117
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、volume、收益序列、时间序列排名、动态生成
- 计算结构：字段 close、high、low、volume；算子 returns、ts_rank；窗口 ts_rank=32、ts_rank=16；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #117。
- 源码计算片段：return _ts_rank(lib.volume, 32) * (1.0 - _ts_rank(lib.close + lib.high - lib.low, 16)) * (1.0 - _ts_rank(lib._returns(), 32))
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、volume 的收益序列、时间序列排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #117。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha117 / 第 996-997 行；总览匹配行 11876
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_118
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、open、滚动求和、动态生成
- 计算结构：字段 high、low、open；算子 ts_sum；窗口 ts_sum=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #118。
- 源码计算片段：return _safe_divide(_ts_sum(lib.high - lib.open, 20), _ts_sum(lib.open - lib.low, 20)) * 100.0
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low、open 的滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #118。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha118 / 第 1000-1001 行；总览匹配行 11888
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_126
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、动态生成
- 计算结构：字段 close、high、low；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #126。
- 源码计算片段：return (lib.close + lib.high + lib.low) / 3.0
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #126。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha126 / 第 1039-1040 行；总览匹配行 11991
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_128
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、volume、历史滞后、滚动求和、动态生成
- 计算结构：字段 close、high、low、volume；算子 delay、ts_sum、where；窗口 ts_sum=14、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #128。
- 源码计算片段：typical = (lib.high + lib.low + lib.close) / 3.0 up = (typical * lib.volume).where(typical > _delay(typical, 1), 0.0) down = (typical * lib.volume).where(typical <= _delay(typical, 1), 0.0) ratio = _safe_divide(_ts_sum(up, 14), _ts_sum(down, 14)) return 100.0 - _safe_divide(100.0, 1.0 + ratio)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、volume 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #128。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha128 / 第 1047-1052 行；总览匹配行 12015
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_133
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、动态生成
- 计算结构：字段 high、low；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #133。
- 源码计算片段：return (20.0 - _highday(lib.high, 20)) / 20.0 * 100.0 - (20.0 - _lowday(lib.low, 20)) / 20.0 * 100.0
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #133。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha133 / 第 1074-1075 行；总览匹配行 12082
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_137
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、open、abs、历史滞后、动态生成
- 计算结构：字段 close、high、low、open；算子 abs、delay、where；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #137。
- 源码计算片段：previous_close = _delay(lib.close, 1) previous_open = _delay(lib.open, 1) a = (lib.high - previous_close).abs() b = (lib.low - previous_close).abs() c = (lib.high - _delay(lib.low, 1)).abs() d = (previous_close - previous_open).abs() condition_a = (a > b) & (a > c) condition_b = (b > c) & (b > a) denominator = pd.DataFrame(np.where(condition_a, a + b / 2.0 + d / 4.0, np.where(condition_b, b + a / 2.0 + d / 4.0, c + d / 4.0)), index=lib.close.index, columns=lib.close.columns) return _safe_divide(16.0 * (lib.close +…
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、open 的abs、历史滞后、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #137。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha137 / 第 1090-1100 行；总览匹配行 12130
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_150
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、volume、动态生成
- 计算结构：字段 close、high、low、volume；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #150。
- 源码计算片段：return (lib.close + lib.high + lib.low) / 3.0 * lib.volume
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、volume 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #150。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha150 / 第 1170-1171 行；总览匹配行 12314
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_156
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：low、open、线性衰减、窗口差分、截面排名、成交量加权价格、动态生成、字段回退
- 计算结构：字段 low、open；算子 decay_linear、delta、rank、vwap；窗口 decay_linear=3、delta=5、delta=2；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #156。
- 源码计算片段：base = lib.open * 0.15 + lib.low * 0.85 first = _rank(_decay_linear(_delta(lib._vwap(), 5), 3)) second = _rank(_decay_linear(_safe_divide(_delta(base, 2), base) - 1.0, 3)) return -_elementwise_max(first, second)
- 本类中的具体角色：它在“日内结构”总论中具体通过 low、open 的线性衰减、窗口差分、截面排名、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #156。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha156 / 第 1200-1204 行；总览匹配行 12392
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_158
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、动态生成
- 计算结构：字段 close、high、low；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #158。
- 源码计算片段：smooth = _sma(lib.close, 15, 2) return _safe_divide((lib.high - smooth) - (lib.low - smooth), lib.close)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #158。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha158 / 第 1215-1217 行；总览匹配行 12423
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_159
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、历史滞后、滚动求和、动态生成
- 计算结构：字段 close、high、low；算子 delay、ts_sum；窗口 delay=1、ts_sum=6、ts_sum=12、ts_sum=24；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #159。
- 源码计算片段：previous = _delay(lib.close, 1) tr = _elementwise_max(lib.high, previous) - _elementwise_min(lib.low, previous) first = _safe_divide(lib.close - _ts_sum(_elementwise_min(lib.low, previous), 6), _ts_sum(tr, 6)) * 12.0 * 24.0 second = _safe_divide(lib.close - _ts_sum(_elementwise_min(lib.low, previous), 12), _ts_sum(tr, 12)) * 6.0 * 24.0 third = _safe_divide(lib.close - _ts_sum(_elementwise_min(lib.low, previous), 24), _ts_sum(tr, 24)) * 6.0 * 24.0 return (first + second + third) * 100.0 / (6.0 * 12.0 + 6.0 * 24.0 +…
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的历史滞后、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #159。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha159 / 第 1220-1226 行；总览匹配行 12436
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_161
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、abs、历史滞后、滚动均值、动态生成
- 计算结构：字段 close、high、low；算子 abs、delay、ts_mean；窗口 delay=1、ts_mean=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #161。
- 源码计算片段：previous = _delay(lib.close, 1) true_range = _elementwise_max(_elementwise_max(lib.high - lib.low, (previous - lib.high).abs()), (previous - lib.low).abs()) return _ts_mean(true_range, 12)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的abs、历史滞后、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #161。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha161 / 第 1233-1236 行；总览匹配行 12465
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_163
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、volume、截面排名、收益序列、滚动均值、动态生成、字段回退
- 计算结构：字段 close、high、volume；算子 rank、returns、ts_mean、vwap；窗口 ts_mean=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #163。
- 源码计算片段：return _rank(-lib._returns() * _ts_mean(lib.volume, 20) * lib._vwap() * (lib.high - lib.close))
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、volume 的截面排名、收益序列、滚动均值、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #163。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha163 / 第 1245-1246 行；总览匹配行 12493
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_164
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、abs、历史滞后、sign、动态生成
- 计算结构：字段 close、high、low；算子 abs、delay、sign、ts_min、where；窗口 delay=1、ts_min=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #164。
- 源码计算片段：previous = _delay(lib.close, 1) change = lib.close - previous safe_change = change.where(change.abs() >= 0.01, np.sign(change) * 0.01) inner = _safe_divide(1.0, safe_change).where(lib.close > previous, 1.0) return _sma(_safe_divide(inner - _ts_min(inner, 12), lib.high - lib.low) * 100.0, 13, 2)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的abs、历史滞后、sign、滚动最小值、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #164。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha164 / 第 1249-1254 行；总览匹配行 12505
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_170
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、volume、历史滞后、截面排名、滚动均值、动态生成、字段回退
- 计算结构：字段 close、high、volume；算子 delay、rank、ts_mean、ts_sum、vwap；窗口 ts_mean=20、ts_sum=5、delay=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #170。
- 源码计算片段：first = _rank(_safe_divide(1.0, lib.close)) * _safe_divide(lib.volume, _ts_mean(lib.volume, 20)) second = _safe_divide(lib.high * _rank(lib.high - lib.close), _ts_sum(lib.high, 5) / 5.0) return first * second - _rank(lib._vwap() - _delay(lib._vwap(), 5))
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、volume 的历史滞后、截面排名、滚动均值、滚动求和、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #170。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha170 / 第 1287-1290 行；总览匹配行 12591
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_171
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、open、动态生成
- 计算结构：字段 close、high、low、open；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #171。
- 源码计算片段：return -_safe_divide((lib.low - lib.close) * lib.open ** 5, (lib.close - lib.high) * lib.close ** 5)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、open 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #171。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha171 / 第 1293-1294 行；总览匹配行 12605
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_175
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、abs、历史滞后、滚动均值、动态生成
- 计算结构：字段 close、high、low；算子 abs、delay、ts_mean；窗口 delay=1、ts_mean=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #175。
- 源码计算片段：previous = _delay(lib.close, 1) true_range = _elementwise_max(_elementwise_max(lib.high - lib.low, (previous - lib.high).abs()), (previous - lib.low).abs()) return _ts_mean(true_range, 6)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的abs、历史滞后、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #175。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha175 / 第 1326-1329 行；总览匹配行 12670
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_177
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、动态生成
- 计算结构：字段 high；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #177。
- 源码计算片段：return (20.0 - _highday(lib.high, 20)) / 20.0 * 100.0
- 本类中的具体角色：它在“日内结构”总论中具体通过 high 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #177。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha177 / 第 1337-1338 行；总览匹配行 12697
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_182
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、open、动态生成
- 计算结构：字段 close、open；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #182。
- 源码计算片段：benchmark_close, benchmark_open = lib._benchmark() same_direction = ((lib.close > lib.open) & (benchmark_close > benchmark_open).to_numpy()[:, None]) | ((lib.close < lib.open) & (benchmark_close < benchmark_open).to_numpy()[:, None]) return _count(same_direction, 20) / 20.0
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、open 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #182。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha182 / 第 1365-1368 行；总览匹配行 12765
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_184
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、open、滚动相关性、历史滞后、截面排名、动态生成
- 计算结构：字段 close、open；算子 corr、delay、rank；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #184。
- 源码计算片段：return _rank(_corr(_delay(lib.open - lib.close, 1), lib.close, 200)) + _rank(lib.open - lib.close)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、open 的滚动相关性、历史滞后、截面排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #184。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha184 / 第 1376-1377 行；总览匹配行 12792
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_185
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、open、截面排名、动态生成
- 计算结构：字段 close、open；算子 rank；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #185。
- 源码计算片段：return _rank(-((1.0 - _safe_divide(lib.open, lib.close)) ** 2))
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、open 的截面排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #185。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha185 / 第 1380-1381 行；总览匹配行 12804
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_187
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、open、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 high、open；算子 delay、ts_sum、where；窗口 delay=1、ts_sum=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #187。
- 源码计算片段：previous_open = _delay(lib.open, 1) return _ts_sum(_elementwise_max(lib.high - lib.open, lib.open - previous_open).where(lib.open > previous_open, 0.0), 20)
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、open 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #187。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha187 / 第 1393-1395 行；总览匹配行 12833
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_188
- 主分类：日内结构
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、动态生成
- 计算结构：字段 high、low；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #188。
- 源码计算片段：hl = lib.high - lib.low smooth = _sma(hl, 11, 2) return _safe_divide(hl - smooth, smooth) * 100.0
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #188。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha188 / 第 1398-1401 行；总览匹配行 12846
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### accumulation_distribution
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、high、low、volume
- 计算结构：字段 close、high、low、volume；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：累积/派发线：按收盘位置加权累计成交量。
- 源码计算片段："""累积/派发线：按收盘位置加权累计成交量。""" multiplier = ((self.close - self.low) - (self.high - self.close)) / ( self.high - self.low + 1e-10 ) return (multiplier * self.volume).cumsum()
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、volume 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点
- 索引说明：累积/派发线：按收盘位置加权累计成交量。
- 来源证据：Factor/libraries/technical_lib.py / accumulation_distribution / 第 342-347 行；总览匹配行 1258、1265、2198
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### aroon_down
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：low、apply、滚动窗口
- 计算结构：字段 low；算子 apply、rolling；窗口 window=26；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：Aroon Down：距离近期最低价出现时间的趋势强度。
- 源码计算片段："""Aroon Down：距离近期最低价出现时间的趋势强度。""" periods_since_low = self.low.rolling(window).apply( lambda values: np.argmin(values[::-1]), raw=True ) return 100 * (window - 1 - periods_since_low) / (window - 1)
- 本类中的具体角色：它在“日内结构”总论中具体通过 low 的apply、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：Aroon Down：距离近期最低价出现时间的趋势强度。
- 来源证据：Factor/libraries/technical_lib.py / aroon_down / 第 170-175 行；总览匹配行 979、986
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### aroon_up
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：high、apply、滚动窗口
- 计算结构：字段 high；算子 apply、rolling；窗口 window=26；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：Aroon Up：距离近期最高价出现时间的趋势强度。
- 源码计算片段："""Aroon Up：距离近期最高价出现时间的趋势强度。""" periods_since_high = self.high.rolling(window).apply( lambda values: np.argmax(values[::-1]), raw=True ) return 100 * (window - 1 - periods_since_high) / (window - 1)
- 本类中的具体角色：它在“日内结构”总论中具体通过 high 的apply、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：Aroon Up：距离近期最高价出现时间的趋势强度。
- 来源证据：Factor/libraries/technical_lib.py / aroon_up / 第 163-168 行；总览匹配行 965、972
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### awesome_oscillator
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：high、low、均值、滚动窗口
- 计算结构：字段 high、low；算子 mean、rolling；窗口 fast=5、slow=34；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：奇妙振荡器：短长周期中间价均线之差。
- 源码计算片段："""奇妙振荡器：短长周期中间价均线之差。""" midpoint = (self.high + self.low) / 2 return midpoint.rolling(fast).mean() - midpoint.rolling(slow).mean()
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：奇妙振荡器：短长周期中间价均线之差。
- 来源证据：Factor/libraries/technical_lib.py / awesome_oscillator / 第 245-248 行；总览匹配行 1103、1110
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### balance_of_power
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、high、low、open
- 计算结构：字段 close、high、low、open；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：平衡交易力量：收盘开盘差相对当日高低价区间。
- 源码计算片段："""平衡交易力量：收盘开盘差相对当日高低价区间。""" return (self.close - self.open) / (self.high - self.low + 1e-10)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、open 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点
- 索引说明：平衡交易力量：收盘开盘差相对当日高低价区间。
- 来源证据：Factor/libraries/technical_lib.py / balance_of_power / 第 250-252 行；总览匹配行 1115、1122
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### cci
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、high、low、abs、apply、均值
- 计算结构：字段 close、high、low；算子 abs、apply、mean、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：商品通道指数：典型价格偏离其平均值的程度。
- 源码计算片段："""商品通道指数：典型价格偏离其平均值的程度。""" typical_price = (self.high + self.low + self.close) / 3 mean = typical_price.rolling(window).mean() mean_deviation = typical_price.rolling(window).apply( lambda values: np.mean(np.abs(values - values.mean())), raw=True ) return (typical_price - mean) / (0.015 * mean_deviation + 1e-10)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的abs、apply、均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：商品通道指数：典型价格偏离其平均值的程度。
- 来源证据：Factor/libraries/technical_lib.py / cci / 第 148-155 行；总览匹配行 613、936、943
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### choppiness_index
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：high、low、clip、滚动最大值、滚动最小值、滚动窗口
- 计算结构：字段 high、low；算子 clip、max、min、rolling、sum；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：混沌指标：衡量市场处于震荡还是方向性趋势。
- 源码计算片段："""混沌指标：衡量市场处于震荡还是方向性趋势。""" true_range_sum = self._true_range().rolling(window).sum() price_range = self.high.rolling(window).max() - self.low.rolling(window).min() ratio = (true_range_sum / (price_range + 1e-10)).clip(lower=1e-10) return 100 * np.log10(ratio) / np.log10(window)
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的clip、滚动最大值、滚动最小值、滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：混沌指标：衡量市场处于震荡还是方向性趋势。
- 来源证据：Factor/libraries/technical_lib.py / choppiness_index / 第 254-259 行；总览匹配行 1126、1133
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### ease_of_movement
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：high、low、volume、diff、均值、滚动窗口
- 计算结构：字段 high、low、volume；算子 diff、mean、rolling；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：简化移动容易度：价格位移相对成交量和振幅的滚动均值。
- 源码计算片段："""简化移动容易度：价格位移相对成交量和振幅的滚动均值。""" distance_moved = ((self.high + self.low) / 2).diff() box_ratio = (self.volume / volume_divisor) / ( self.high - self.low + 1e-10 ) one_period = distance_moved / (box_ratio + 1e-10) return one_period.rolling(window).mean()
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low、volume 的diff、均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：简化移动容易度：价格位移相对成交量和振幅的滚动均值。
- 来源证据：Factor/libraries/technical_lib.py / ease_of_movement / 第 216-223 行；总览匹配行 1060、1067
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### fisher_transform
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：high、low、clip、log、滚动最大值、滚动最小值
- 计算结构：字段 high、low；算子 clip、log、max、min、rolling、where；窗口 window=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：费舍尔变换：滚动中点价格归一化后的非线性振荡器。
- 源码计算片段："""费舍尔变换：滚动中点价格归一化后的非线性振荡器。""" midpoint = (self.high + self.low) / 2 lowest = midpoint.rolling(window).min() highest = midpoint.rolling(window).max() price_range = highest - lowest normalized = ( 2 * (midpoint - lowest) / (price_range + 1e-10) - 1 ).where(price_range > 0, 0.0) normalized = normalized.clip(-0.999999, 0.999999) return 0.5 * np.log((1 + normalized) / (1 - normalized))
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的clip、log、滚动最大值、滚动最小值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：费舍尔变换：滚动中点价格归一化后的非线性振荡器。
- 来源证据：Factor/libraries/technical_lib.py / fisher_transform / 第 204-214 行；总览匹配行 1041、1048
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### kdj_d
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、high、low、滚动最大值、均值、滚动最小值
- 计算结构：字段 close、high、low；算子 max、mean、min、rolling；窗口 window=9；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：KDJ D 值。
- 源码计算片段："""KDJ D 值。""" hh = self.high.rolling(window).max() ll = self.low.rolling(window).min() k = (self.close - ll) / (hh - ll + 1e-10) * 100 return k.rolling(k_smooth).mean()
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动最大值、均值、滚动最小值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：KDJ D 值。
- 来源证据：Factor/libraries/technical_lib.py / kdj_d / 第 134-139 行；总览匹配行 904、912
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### kdj_k
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、high、low、滚动最大值、滚动最小值、滚动窗口
- 计算结构：字段 close、high、low；算子 max、min、rolling；窗口 window=9；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：KDJ K 值。
- 源码计算片段："""KDJ K 值。""" hh = self.high.rolling(window).max() ll = self.low.rolling(window).min() return (self.close - ll) / (hh - ll + 1e-10) * 100
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动最大值、滚动最小值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：KDJ K 值。
- 来源证据：Factor/libraries/technical_lib.py / kdj_k / 第 128-132 行；总览匹配行 889、897
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### overnight_gap_follow_through
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、open、abs、均值、滚动窗口、历史位移
- 计算结构：字段 close、open；算子 abs、mean、rolling、shift、where；窗口 window=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：隔夜跳空延续：跳空方向与当日盘中收益方向一致性的滚动均值。
- 源码计算片段："""隔夜跳空延续：跳空方向与当日盘中收益方向一致性的滚动均值。""" window = self._validate_window(window) previous_close = self.close.shift() gap = (self.open - previous_close) / (previous_close.abs() + 1e-10) intraday_return = (self.close - self.open) / (self.open.abs() + 1e-10) gap_direction = gap.gt(0).astype(float) - gap.lt(0).astype(float) continuation = (gap_direction * intraday_return).where( gap.notna() & intraday_return.notna() ) return continuation.rolling(window).mean()
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、open 的abs、均值、滚动窗口、历史位移、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：隔夜跳空延续：跳空方向与当日盘中收益方向一致性的滚动均值。
- 来源证据：Factor/libraries/technical_lib.py / overnight_gap_follow_through / 第 393-403 行；总览匹配行 1368、1377
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### overnight_gap_share
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、open、abs、clip、滚动窗口、历史位移
- 计算结构：字段 close、open；算子 abs、clip、rolling、shift、sum、where；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：隔夜跳空占比：隔夜跳空绝对幅度占真实区间总量的比例。
- 源码计算片段："""隔夜跳空占比：隔夜跳空绝对幅度占真实区间总量的比例。""" window = self._validate_window(window) previous_close = self.close.shift() gap_size = (self.open - previous_close).abs() true_range = self._true_range() numerator = gap_size.rolling(window).sum() denominator = true_range.rolling(window).sum() result = numerator / (denominator + 1e-10) result = result.where(numerator.notna() & denominator.notna()) return result.where( denominator.isna() | (denominator > 1e-10), 0.0 ).clip(lower=0.0, upper=1.0)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、open 的abs、clip、滚动窗口、历史位移、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：隔夜跳空占比：隔夜跳空绝对幅度占真实区间总量的比例。
- 来源证据：Factor/libraries/technical_lib.py / overnight_gap_share / 第 504-516 行；总览匹配行 1538、1547
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### price_pattern_doji
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、high、low、open、abs
- 计算结构：字段 close、high、low、open；算子 abs；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：十字星形态。
- 源码计算片段："""十字星形态。""" body = (self.open - self.close).abs() shadow = self.high - self.low return (body / (shadow + 1e-10) < 0.1).astype(float)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、open 的abs实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点
- 索引说明：十字星形态。
- 来源证据：Factor/libraries/technical_lib.py / price_pattern_doji / 第 351-355 行；总览匹配行 1272、1280
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### price_pattern_hammer
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、high、low、open、abs
- 计算结构：字段 close、high、low、open；算子 abs；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：锤子线形态。
- 源码计算片段："""锤子线形态。""" body = (self.open - self.close).abs() lower_shadow = self.close - self.low upper_shadow = self.high - self.open return ((lower_shadow > body * 2) & (upper_shadow < body * 0.5)).astype(float)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、open 的abs实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点
- 索引说明：锤子线形态。
- 来源证据：Factor/libraries/technical_lib.py / price_pattern_hammer / 第 357-362 行；总览匹配行 1287、1295
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### relative_vigor_index
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、high、low、open、均值、滚动窗口
- 计算结构：字段 close、high、low、open；算子 mean、rolling、shift；窗口 shift=3、shift=2、shift=1、window=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：相对活力指数：收盘—开盘动量相对高低价区间的平滑比值。
- 源码计算片段："""相对活力指数：收盘—开盘动量相对高低价区间的平滑比值。""" close_open = self.close - self.open high_low = self.high - self.low numerator = ( close_open + 2 * close_open.shift(1) + 2 * close_open.shift(2) + close_open.shift(3) ) / 6 denominator = ( high_low + 2 * high_low.shift(1) + 2 * high_low.shift(2) + high_low.shift(3) ) / 6 return numerator.rolling(window).mean() / ( denominator.rolling(window).mean() + 1e-10 )
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、open 的均值、滚动窗口、历史位移实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：相对活力指数：收盘—开盘动量相对高低价区间的平滑比值。
- 来源证据：Factor/libraries/technical_lib.py / relative_vigor_index / 第 225-243 行；总览匹配行 1076、1083
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### ultimate_oscillator
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、high、low、滚动窗口、历史位移、求和
- 计算结构：字段 close、high、low；算子 rolling、shift、sum、where；窗口 short=7、long=28；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：终极振荡器：多周期买压与真实波幅的加权动量。
- 源码计算片段："""终极振荡器：多周期买压与真实波幅的加权动量。""" previous_close = self.close.shift() minimum = self.low.where(self.low <= previous_close, previous_close) maximum = self.high.where(self.high >= previous_close, previous_close) buying_pressure = self.close - minimum true_range = maximum - minimum def average(window: int): return buying_pressure.rolling(window).sum() / ( true_range.rolling(window).sum() + 1e-10 ) return 100 * (4 * average(short) + 2 * average(medium) + average(long)) / 7
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动窗口、历史位移、求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：终极振荡器：多周期买压与真实波幅的加权动量。
- 来源证据：Factor/libraries/technical_lib.py / ultimate_oscillator / 第 189-202 行；总览匹配行 1019、1026
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vortex_indicator
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：high、low、abs、滚动窗口、历史位移、求和
- 计算结构：字段 high、low；算子 abs、rolling、shift、sum；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：涡旋指标差：上行与下行涡旋线之差。
- 源码计算片段："""涡旋指标差：上行与下行涡旋线之差。""" previous_low = self.low.shift() previous_high = self.high.shift() positive_movement = (self.high - previous_low).abs() negative_movement = (self.low - previous_high).abs() true_range = self._true_range() true_range_sum = true_range.rolling(window).sum() positive = positive_movement.rolling(window).sum() / (true_range_sum + 1e-10) negative = negative_movement.rolling(window).sum() / (true_range_sum + 1e-10) return positive - negative
- 本类中的具体角色：它在“日内结构”总论中具体通过 high、low 的abs、滚动窗口、历史位移、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：涡旋指标差：上行与下行涡旋线之差。
- 来源证据：Factor/libraries/technical_lib.py / vortex_indicator / 第 295-305 行；总览匹配行 1202、1209
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### wick_reversal_pressure
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、high、low、open、clip、均值
- 计算结构：字段 close、high、low、open；算子 clip、mean、rolling、where；窗口 window=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：影线反转压力：下影线相对上影线的滚动不平衡。
- 源码计算片段："""影线反转压力：下影线相对上影线的滚动不平衡。""" window = self._validate_window(window) body_top = self.open.where(self.open >= self.close, self.close) body_bottom = self.open.where(self.open <= self.close, self.close) upper_shadow = (self.high - body_top).clip(lower=0.0) lower_shadow = (body_bottom - self.low).clip(lower=0.0) price_range = self.high - self.low valid_range = price_range.notna() & price_range.ge(0.0) safe_range = price_range.where(price_range > 0.0, 1e-10) pressure = ((lower_shadow - upper_shadow) / safe_range).where(…
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low、open 的clip、均值、滚动窗口、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：影线反转压力：下影线相对上影线的滚动不平衡。
- 来源证据：Factor/libraries/technical_lib.py / wick_reversal_pressure / 第 491-502 行；总览匹配行 1515、1524
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### williams_r
- 主分类：日内结构
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、high、low、滚动最大值、滚动最小值、滚动窗口
- 计算结构：字段 close、high、low；算子 max、min、rolling；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：Williams %R：收盘价在近期高低区间中的位置。
- 源码计算片段："""Williams %R：收盘价在近期高低区间中的位置。""" highest_high = self.high.rolling(window).max() lowest_low = self.low.rolling(window).min() return -100 * (highest_high - self.close) / (highest_high - lowest_low + 1e-10)
- 本类中的具体角色：它在“日内结构”总论中具体通过 close、high、low 的滚动最大值、滚动最小值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：Williams %R：收盘价在近期高低区间中的位置。
- 来源证据：Factor/libraries/technical_lib.py / williams_r / 第 157-161 行；总览匹配行 952、959
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### alpha005
- 主分类：日内结构
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、open、abs、截面排名、滚动求和、成交量加权价格、动态生成、字段回退
- 计算结构：字段 close、open；算子 abs、rank、ts_sum、vwap；窗口 ts_sum=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：vwap 偏离的排名变化；核心算子：rank, ts_rank, vwap。
- 源码计算片段：vwap = _vwap(library) return _rank(library.open - _ts_sum(vwap, 10) / 10.0) * -_rank( library.close - vwap ).abs()
- 本类中的具体角色：文章来源把它概括为“vwap 偏离的排名变化”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：利用 close、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #005。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha005 / 第 284-288 行；总览匹配行 8436
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha041
- 主分类：日内结构
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、low、sqrt、成交量加权价格、动态生成、字段回退
- 计算结构：字段 high、low；算子 sqrt、vwap；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：文章逻辑：日内振幅与 vwap 的关系；核心算子：high, low, vwap。
- 源码计算片段：return np.sqrt(library.high * library.low) - _vwap(library)
- 本类中的具体角色：文章来源把它概括为“日内振幅与 vwap 的关系”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：利用 high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #041。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha041 / 第 558-559 行；总览匹配行 8356、8372、8998
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha042
- 主分类：日内结构
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、截面排名、成交量加权价格、动态生成、字段回退
- 计算结构：字段 close；算子 rank、vwap；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：文章逻辑：vwap 与收盘价偏离；核心算子：rank, vwap, close。
- 源码计算片段：vwap = _vwap(library) return _safe_divide(_rank(vwap - library.close), _rank(vwap + library.close))
- 本类中的具体角色：文章来源把它概括为“vwap 与收盘价偏离”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：利用 close 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #042。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha042 / 第 562-564 行；总览匹配行 9010
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha047
- 主分类：日内结构
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、volume、平均成交额/成交量、历史滞后、截面排名、动态生成、字段回退
- 计算结构：字段 close、high、volume；算子 adv、delay、rank、ts_sum、vwap；窗口 adv=20、delay=5、ts_sum=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：流动性加权的 vwap-close 偏离；核心算子：rank, adv, high, close, vwap。
- 源码计算片段：return ( _safe_divide(_rank(_safe_divide(1.0, library.close)) * library.volume, _adv(library, 20)) * _safe_divide( library.high * _rank(library.high - library.close), _ts_sum(library.high, 5) / 5.0, ) - _rank(_vwap(library) - _delay(_vwap(library), 5)) )
- 本类中的具体角色：文章来源把它概括为“流动性加权的 vwap-close 偏离”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：利用 close、high、volume 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、volume；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #047。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha047 / 第 599-607 行；总览匹配行 9087
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha054
- 主分类：日内结构
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、open、动态生成
- 计算结构：字段 close、high、low、open；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：文章逻辑：日内偏离结构；核心算子：open, close, low。
- 源码计算片段：numerator = (library.low - library.close) * np.power(library.open, 5) denominator = (library.low - library.high) * np.power(library.close, 5) return -_safe_divide(numerator, denominator)
- 本类中的具体角色：文章来源把它概括为“日内偏离结构”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：利用 close、high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #054。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha054 / 第 659-662 行；总览匹配行 9203
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha062
- 主分类：日内结构
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、low、open、平均成交额/成交量、滚动相关性、截面排名、动态生成、字段回退
- 计算结构：字段 high、low、open；算子 adv、correlation、rank、ts_sum、vwap；窗口 correlation=9.91009、ts_sum=22.4101、adv=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：vwap 排名 × 量价相关；核心算子：rank, vwap, correlation, adv。
- 源码计算片段：left = _rank( _correlation(vwap := _vwap(library), _ts_sum(_adv(library, 20), 22.4101), 9.91009) ) right = _rank( (_rank(library.open) + _rank(library.open)) < (_rank((library.high + library.low) / 2.0) + _rank(library.high)) ) return _bool_signal(left < right, -1.0)
- 本类中的具体角色：文章来源把它概括为“vwap 排名 × 量价相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：利用 high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #062。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha062 / 第 724-732 行；总览匹配行 9332
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha064
- 主分类：日内结构
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、low、open、平均成交额/成交量、滚动相关性、窗口差分、动态生成、字段回退
- 计算结构：字段 high、low、open；算子 adv、correlation、delta、rank、ts_sum、vwap；窗口 correlation=16.6208、delta=3.69741、ts_sum=12.7054、adv=120；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：vwap 流动性相关排名；核心算子：rank, correlation, vwap, adv。
- 源码计算片段：first = library.open * 0.178404 + library.low * (1 - 0.178404) second = (library.high + library.low) / 2.0 * 0.178404 + _vwap(library) * (1 - 0.178404) left = _rank( _correlation( _ts_sum(first, 12.7054), _ts_sum(_adv(library, 120), 12.7054), 16.6208, ) ) right = _rank(_delta(second, 3.69741)) return _bool_signal(left < right, -1.0)
- 本类中的具体角色：文章来源把它概括为“vwap 流动性相关排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：利用 high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；文章分类表标记 IndNeut，但当前源码局部未检测到对应调用，需人工复核
- 索引说明：WorldQuant Formulaic Alpha #064。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha064 / 第 756-767 行；总览匹配行 9380
- 与因子库总览一致性：mentioned
- 语义置信度：中：文章分类与当前实现标记存在差异

### alpha065
- 主分类：日内结构
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：open、平均成交额/成交量、滚动相关性、截面排名、滚动最小值、滚动求和、动态生成、字段回退
- 计算结构：字段 open；算子 adv、correlation、rank、ts_min、ts_sum、vwap；窗口 correlation=6.40374、ts_sum=8.6911、ts_min=13.635、adv=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：vwap 排名相关性衰减；核心算子：rank, correlation, vwap, adv。
- 源码计算片段：first = library.open * 0.00817205 + _vwap(library) * (1 - 0.00817205) left = _rank( _correlation(first, _ts_sum(_adv(library, 60), 8.6911), 6.40374) ) right = _rank(library.open - _ts_min(library.open, 13.635)) return _bool_signal(left < right, -1.0)
- 本类中的具体角色：文章来源把它概括为“vwap 排名相关性衰减”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：利用 open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；文章分类表标记 IndNeut，但当前源码局部未检测到对应调用，需人工复核
- 索引说明：WorldQuant Formulaic Alpha #065。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha065 / 第 770-776 行；总览匹配行 9402
- 与因子库总览一致性：mentioned
- 语义置信度：中：文章分类与当前实现标记存在差异

### alpha066
- 主分类：日内结构
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、low、open、线性衰减、窗口差分、截面排名、动态生成、字段回退
- 计算结构：字段 high、low、open；算子 decay_linear、delta、rank、ts_rank、vwap；窗口 ts_rank=6.72611、decay_linear=7.23052、decay_linear=11.4157、delta=3.51013；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：vwap 偏离的衰减动量；核心算子：rank, decay_linear, vwap, delta。
- 源码计算片段：vwap = _vwap(library) second = _safe_divide( library.low * 0.96633 + library.low * (1 - 0.96633) - vwap, library.open - (library.high + library.low) / 2.0, ) value = _rank(_decay_linear(_delta(vwap, 3.51013), 7.23052)) + _ts_rank( _decay_linear(second, 11.4157), 6.72611 ) return -value
- 本类中的具体角色：文章来源把它概括为“vwap 偏离的衰减动量”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：利用 high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；文章分类表标记 IndNeut，但当前源码局部未检测到对应调用，需人工复核
- 索引说明：WorldQuant Formulaic Alpha #066。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha066 / 第 779-788 行；总览匹配行 9419
- 与因子库总览一致性：mentioned
- 语义置信度：中：文章分类与当前实现标记存在差异

### alpha068
- 主分类：日内结构
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、平均成交额/成交量、滚动相关性、窗口差分、动态生成、字段回退
- 计算结构：字段 close、high、low；算子 adv、correlation、delta、rank、ts_rank；窗口 ts_rank=13.9333、correlation=8.91644、delta=1.06157、adv=15；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：最高价-均量相关 × 收盘排名；核心算子：rank, correlation, high, adv, close。
- 源码计算片段：left = _ts_rank( _correlation(_rank(library.high), _rank(_adv(library, 15)), 8.91644), 13.9333, ) right = _rank( _delta(library.close * 0.518371 + library.low * (1 - 0.518371), 1.06157) ) return _bool_signal(left < right, -1.0)
- 本类中的具体角色：文章来源把它概括为“最高价-均量相关 × 收盘排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：利用 close、high、low 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；文章分类表标记 IndNeut，但当前源码局部未检测到对应调用，需人工复核
- 索引说明：WorldQuant Formulaic Alpha #068。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha068 / 第 803-811 行；总览匹配行 9459
- 与因子库总览一致性：mentioned
- 语义置信度：中：文章分类与当前实现标记存在差异

### alpha073
- 主分类：日内结构
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：low、open、线性衰减、窗口差分、截面排名、时间序列排名、动态生成、字段回退
- 计算结构：字段 low、open；算子 decay_linear、delta、rank、ts_rank、vwap；窗口 ts_rank=16.7411、decay_linear=2.91864、decay_linear=3.33829、delta=4.72775、delta=2.03608；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：vwap 衰减 × 开盘变化；核心算子：rank, decay_linear, vwap, delta, open。
- 源码计算片段：vwap = _vwap(library) first = _rank(_decay_linear(_delta(vwap, 4.72775), 2.91864)) weighted = library.open * 0.147155 + library.low * (1 - 0.147155) second = _ts_rank( _decay_linear(-_safe_divide(_delta(weighted, 2.03608), weighted), 3.33829), 16.7411, ) return -np.maximum(first, second)
- 本类中的具体角色：文章来源把它概括为“vwap 衰减 × 开盘变化”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：利用 low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；文章分类表标记 IndNeut，但当前源码局部未检测到对应调用，需人工复核
- 索引说明：WorldQuant Formulaic Alpha #073。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha073 / 第 887-895 行；总览匹配行 9583
- 与因子库总览一致性：mentioned
- 语义置信度：中：文章分类与当前实现标记存在差异

### alpha101
- 主分类：日内结构
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、open、动态生成
- 计算结构：字段 close、high、low、open；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：文章逻辑：日内收益占振幅比；核心算子：close, open, high, low。
- 源码计算片段：return _safe_divide( library.close - library.open, library.high - library.low + 0.001, epsilon=0.0, )
- 本类中的具体角色：文章来源把它概括为“日内收益占振幅比”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：利用 close、high、low、open 的同日相对位置描述开盘、收盘、最高/最低价或 VWAP 之间的关系；它关注日内强弱和收盘位置，而不是单纯的长期收益。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于 OHLC/VWAP 日内位置关系解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #101。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha101 / 第 1358-1363 行；总览匹配行 6、54、56
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

## 量价背离

> 因子数量：96；来源分布：gtja_alpha191 54、worldquant_alpha101 32、alpha_features 10

价格和成交信息是否同步。价格上涨但成交没有跟上，或成交突然放大而价格没有继续移动，都被视为需要解释的量价不一致。 研究假设是：量价背离可能意味着趋势缺乏确认、短期交易过热，或者大资金在不显眼地完成建仓；因此本类既包含反转视角，也包含对资金参与度的确认视角。

常见表达是 rank(open/close/high/low) 与 rank(volume/adv) 的 correlation/covariance，或 sign(delta(volume, 1)) 与 delta(close, 1) 的符号交互；rank 负责横截面可比，rolling correlation 负责观察一段时间的同步程度。 方向不能脱离最终符号判断。原文章中 Alpha#3 的 -correlation(rank(open), rank(volume), 10) 用正值表达更强的量价背离；Alpha#12 则用成交量变化方向反转价格变化，说明同一类中也可能存在不同的交易假设。

Alpha#3 观察开盘价排名与成交量排名的 10 日相关性；Alpha#12 观察放量/缩量与价格变化方向的反向关系。两者共同说明本类关注的不是单一价格趋势，而是“价格变化是否得到成交确认”。

边界上，依赖 volume、amount 或 adv 的口径；A 股中成交额、换手率、复权价格和停牌处理会改变量价关系。使用收盘数据时还要明确生成信号和次日执行的时点。

### Alpha158 CORD 公式族（5 个参数变体）

这组因子的共同公式是 `rolling(corr(close / close.shift(1), log(volume / volume.shift(1) + 1)), {window})`。共同输入字段为 close、volume，主要算子为 shift、rolling、correlation、log；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“量价背离”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_cord5、alpha158_cord10、alpha158_cord20、alpha158_cord30、alpha158_cord60。

**因子：alpha158_cord5**
- 主分类：量价背离
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、历史位移、滚动窗口、滚动相关性、log、动态生成
- 本条参数差异：沿用上述“Alpha158 CORD 公式族”；本因子参数为 window=5。
- 计算结构：字段 close、volume；算子 shift、rolling、correlation、log；窗口 shift=1、rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CORD5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7677、7683
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cord10**
- 主分类：量价背离
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、历史位移、滚动窗口、滚动相关性、log、动态生成
- 本条参数差异：沿用上述“Alpha158 CORD 公式族”；本因子参数为 window=10。
- 计算结构：字段 close、volume；算子 shift、rolling、correlation、log；窗口 shift=1、rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CORD10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7687、7693
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cord20**
- 主分类：量价背离
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、历史位移、滚动窗口、滚动相关性、log、动态生成
- 本条参数差异：沿用上述“Alpha158 CORD 公式族”；本因子参数为 window=20。
- 计算结构：字段 close、volume；算子 shift、rolling、correlation、log；窗口 shift=1、rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CORD20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7697、7703
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cord30**
- 主分类：量价背离
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、历史位移、滚动窗口、滚动相关性、log、动态生成
- 本条参数差异：沿用上述“Alpha158 CORD 公式族”；本因子参数为 window=30。
- 计算结构：字段 close、volume；算子 shift、rolling、correlation、log；窗口 shift=1、rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CORD30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7707、7713
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_cord60**
- 主分类：量价背离
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、历史位移、滚动窗口、滚动相关性、log、动态生成
- 本条参数差异：沿用上述“Alpha158 CORD 公式族”；本因子参数为 window=60。
- 计算结构：字段 close、volume；算子 shift、rolling、correlation、log；窗口 shift=1、rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CORD60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7717、7723
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 CORR 公式族（5 个参数变体）

这组因子的共同公式是 `close.rolling({window}, min_periods=1).corr(log(volume + 1))`。共同输入字段为 close、volume，主要算子为 rolling、correlation、log；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“量价背离”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_corr5、alpha158_corr10、alpha158_corr20、alpha158_corr30、alpha158_corr60。

**因子：alpha158_corr5**
- 主分类：量价背离
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、滚动窗口、滚动相关性、log、动态生成
- 本条参数差异：沿用上述“Alpha158 CORR 公式族”；本因子参数为 window=5。
- 计算结构：字段 close、volume；算子 rolling、correlation、log；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CORR5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7627、7633
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_corr10**
- 主分类：量价背离
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、滚动窗口、滚动相关性、log、动态生成
- 本条参数差异：沿用上述“Alpha158 CORR 公式族”；本因子参数为 window=10。
- 计算结构：字段 close、volume；算子 rolling、correlation、log；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CORR10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7637、7643
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_corr20**
- 主分类：量价背离
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、滚动窗口、滚动相关性、log、动态生成
- 本条参数差异：沿用上述“Alpha158 CORR 公式族”；本因子参数为 window=20。
- 计算结构：字段 close、volume；算子 rolling、correlation、log；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CORR20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7647、7653
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_corr30**
- 主分类：量价背离
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、滚动窗口、滚动相关性、log、动态生成
- 本条参数差异：沿用上述“Alpha158 CORR 公式族”；本因子参数为 window=30。
- 计算结构：字段 close、volume；算子 rolling、correlation、log；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CORR30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7657、7663
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_corr60**
- 主分类：量价背离
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、滚动窗口、滚动相关性、log、动态生成
- 本条参数差异：沿用上述“Alpha158 CORR 公式族”；本因子参数为 window=60。
- 计算结构：字段 close、volume；算子 rolling、correlation、log；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 CORR60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7667、7673
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_001
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、open、volume、滚动相关性、窗口差分、log、动态生成
- 计算结构：字段 close、open、volume；算子 corr、delta、log、rank；窗口 delta=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #001。
- 源码计算片段：return -_corr(_rank(_delta(np.log(lib.volume), 1)), _rank(_safe_divide(lib.close - lib.open, lib.open)), 6)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、open、volume 的滚动相关性、窗口差分、log、截面排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、窗口差分、log、截面排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #001。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha001 / 第 372-373 行；总览匹配行 7、10300、10310
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_005
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、volume、滚动相关性、滚动最大值、时间序列排名、动态生成
- 计算结构：字段 high、volume；算子 corr、ts_max、ts_rank；窗口 ts_max=3、ts_rank=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #005。
- 源码计算片段：return -_ts_max(_corr(_ts_rank(lib.volume, 5), _ts_rank(lib.high, 5), 5), 3)
- 本类中的具体角色：它在“量价背离”总论中具体通过 high、volume 的滚动相关性、滚动最大值、时间序列排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、滚动最大值、时间序列排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #005。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha005 / 第 405-406 行；总览匹配行 10389
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_007
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、窗口差分、截面排名、滚动最大值、滚动最小值、动态生成、字段回退
- 计算结构：字段 close、volume；算子 delta、rank、ts_max、ts_min、vwap；窗口 delta=3、ts_max=3、ts_min=3；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #007。
- 源码计算片段：spread = lib._vwap() - lib.close return (_rank(_ts_max(spread, 3)) + _rank(_ts_min(spread, 3))) * _rank(_delta(lib.volume, 3))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、volume 的窗口差分、截面排名、滚动最大值、滚动最小值、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；窗口差分、截面排名、滚动最大值、滚动最小值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #007。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha007 / 第 413-415 行；总览匹配行 10413
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_010
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、截面排名、收益序列、滚动最大值、滚动波动率、where、动态生成
- 计算结构：字段 close；算子 rank、returns、ts_max、ts_std、where；窗口 ts_max=5、ts_std=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #010。
- 源码计算片段：returns = lib._returns() selected = _ts_std(returns, 20).where(returns < 0, lib.close) return _rank(_ts_max(selected ** 2, 5))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close 的截面排名、收益序列、滚动最大值、滚动波动率、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close 的相对变化或联动，重点观察价格与成交信息是否同步；截面排名、收益序列、滚动最大值、滚动波动率、where 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #010。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha010 / 第 428-431 行；总览匹配行 10311、10452
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_016
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：volume、滚动相关性、截面排名、滚动最大值、成交量加权价格、动态生成、字段回退
- 计算结构：字段 volume；算子 corr、rank、ts_max、vwap；窗口 ts_max=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #016。
- 源码计算片段：return -_ts_max(_rank(_corr(_rank(lib.volume), _rank(lib._vwap()), 5)), 5)
- 本类中的具体角色：它在“量价背离”总论中具体通过 volume 的滚动相关性、截面排名、滚动最大值、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动最大值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #016。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha016 / 第 454-455 行；总览匹配行 10526
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_017
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、窗口差分、截面排名、保留符号幂、滚动最大值、成交量加权价格、动态生成、字段回退
- 计算结构：字段 close；算子 delta、rank、signed_power、ts_max、vwap；窗口 delta=5、ts_max=15；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #017。
- 源码计算片段：return _signed_power(_rank(lib._vwap() - _ts_max(lib._vwap(), 15)), _delta(lib.close, 5))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close 的窗口差分、截面排名、保留符号幂、滚动最大值、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close 的相对变化或联动，重点观察价格与成交信息是否同步；窗口差分、截面排名、保留符号幂、滚动最大值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #017。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha017 / 第 458-459 行；总览匹配行 10538
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_025
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、线性衰减、窗口差分、截面排名、收益序列、动态生成
- 计算结构：字段 close、volume；算子 decay_linear、delta、rank、returns、ts_mean、ts_sum；窗口 ts_sum=250、delta=7、decay_linear=9、ts_mean=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #025。
- 源码计算片段：return -_rank(_delta(lib.close, 7) * (1.0 - _rank(_decay_linear(_safe_divide(lib.volume, _ts_mean(lib.volume, 20)), 9)))) * (1.0 + _rank(_ts_sum(lib._returns(), 250)))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、volume 的线性衰减、窗口差分、截面排名、收益序列、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；线性衰减、窗口差分、截面排名、收益序列、滚动均值、滚动求和 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #025。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha025 / 第 500-501 行；总览匹配行 10644
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_032
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、volume、滚动相关性、截面排名、滚动求和、动态生成
- 计算结构：字段 high、volume；算子 corr、rank、ts_sum；窗口 ts_sum=3；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #032。
- 源码计算片段：return -_ts_sum(_rank(_corr(_rank(lib.high), _rank(lib.volume), 3)), 3)
- 本类中的具体角色：它在“量价背离”总论中具体通过 high、volume 的滚动相关性、截面排名、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动求和 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #032。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha032 / 第 535-536 行；总览匹配行 10735
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_035
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：open、volume、滚动相关性、线性衰减、窗口差分、截面排名、动态生成
- 计算结构：字段 open、volume；算子 corr、decay_linear、delta、rank；窗口 decay_linear=15、decay_linear=7、delta=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #035。
- 源码计算片段：left = _rank(_decay_linear(_delta(lib.open, 1), 15)) right = _rank(_decay_linear(_corr(lib.volume, lib.open, 17), 7)) return _elementwise_min(left, right)
- 本类中的具体角色：它在“量价背离”总论中具体通过 open、volume 的滚动相关性、线性衰减、窗口差分、截面排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、线性衰减、窗口差分、截面排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #035。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha035 / 第 548-551 行；总览匹配行 10772
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_036
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：volume、滚动相关性、截面排名、滚动求和、成交量加权价格、动态生成、字段回退
- 计算结构：字段 volume；算子 corr、rank、ts_sum、vwap；窗口 ts_sum=2；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #036。
- 源码计算片段：return _rank(_ts_sum(_corr(_rank(lib.volume), _rank(lib._vwap()), 6), 2))
- 本类中的具体角色：它在“量价背离”总论中具体通过 volume 的滚动相关性、截面排名、滚动求和、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动求和、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #036。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha036 / 第 554-555 行；总览匹配行 10786
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_039
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、open、volume、滚动相关性、线性衰减、窗口差分、动态生成、字段回退
- 计算结构：字段 close、open、volume；算子 corr、decay_linear、delta、rank、ts_mean、ts_sum、vwap；窗口 decay_linear=8、decay_linear=12、delta=2、ts_sum=37、ts_mean=180；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #039。
- 源码计算片段：first = _rank(_decay_linear(_delta(lib.close, 2), 8)) second = _rank(_decay_linear(_corr(lib._vwap() * 0.3 + lib.open * 0.7, _ts_sum(_ts_mean(lib.volume, 180), 37), 14), 12)) return first - second
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、open、volume 的滚动相关性、线性衰减、窗口差分、截面排名、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、线性衰减、窗口差分、截面排名、滚动均值、滚动求和 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #039。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha039 / 第 567-570 行；总览匹配行 10823
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_041
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：open、high、low、close、volume、窗口差分、动态生成、字段回退
- 计算结构：字段 open、high、low、close、volume；算子 delta、rank、ts_max、vwap；窗口 ts_max=5、delta=3；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #041。
- 源码计算片段：return -_rank(_ts_max(_delta(lib._vwap(), 3), 5))
- 本类中的具体角色：它在“量价背离”总论中具体通过 源码局部未识别字段 的窗口差分、截面排名、滚动最大值、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 open、high、low、close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；窗口差分、截面排名、滚动最大值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 open、high、low、close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #041。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha041 / 第 579-580 行；总览匹配行 10851
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_042
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、volume、滚动相关性、截面排名、滚动波动率、动态生成
- 计算结构：字段 high、volume；算子 corr、rank、ts_std；窗口 ts_std=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #042。
- 源码计算片段：return -_rank(_ts_std(lib.high, 10)) * _corr(lib.high, lib.volume, 10)
- 本类中的具体角色：它在“量价背离”总论中具体通过 high、volume 的滚动相关性、截面排名、滚动波动率实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动波动率 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #042。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha042 / 第 583-584 行；总览匹配行 10863
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_044
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：low、volume、滚动相关性、线性衰减、窗口差分、滚动均值、动态生成、字段回退
- 计算结构：字段 low、volume；算子 corr、decay_linear、delta、ts_mean、ts_rank、vwap；窗口 ts_rank=4、ts_rank=15、decay_linear=6、decay_linear=10、delta=3、ts_mean=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #044。
- 源码计算片段：return _ts_rank(_decay_linear(_corr(lib.low, _ts_mean(lib.volume, 10), 7), 6), 4) + _ts_rank(_decay_linear(_delta(lib._vwap(), 3), 10), 15)
- 本类中的具体角色：它在“量价背离”总论中具体通过 low、volume 的滚动相关性、线性衰减、窗口差分、滚动均值、时间序列排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、线性衰减、窗口差分、滚动均值、时间序列排名、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #044。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha044 / 第 593-594 行；总览匹配行 10889
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_045
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、open、volume、滚动相关性、窗口差分、截面排名、动态生成、字段回退
- 计算结构：字段 close、open、volume；算子 corr、delta、rank、ts_mean、vwap；窗口 delta=1、ts_mean=150；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #045。
- 源码计算片段：return _rank(_delta(lib.close * 0.6 + lib.open * 0.4, 1)) * _rank(_corr(lib._vwap(), _ts_mean(lib.volume, 150), 15))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、open、volume 的滚动相关性、窗口差分、截面排名、滚动均值、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、窗口差分、截面排名、滚动均值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #045。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha045 / 第 597-598 行；总览匹配行 10901
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_048
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、历史滞后、截面排名、sign、滚动求和、动态生成
- 计算结构：字段 close、volume；算子 delay、rank、sign、ts_sum；窗口 ts_sum=5、ts_sum=20、delay=2、delay=3、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #048。
- 源码计算片段：signed = np.sign(lib.close - _delay(lib.close, 1)) + np.sign(_delay(lib.close, 1) - _delay(lib.close, 2)) + np.sign(_delay(lib.close, 2) - _delay(lib.close, 3)) return -_rank(signed) * _safe_divide(_ts_sum(lib.volume, 5), _ts_sum(lib.volume, 20))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、volume 的历史滞后、截面排名、sign、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；历史滞后、截面排名、sign、滚动求和 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #048。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha048 / 第 610-612 行；总览匹配行 10938
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_056
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、open、volume、滚动相关性、动态生成
- 计算结构：字段 close、high、low、open、volume；算子 corr、rank、ts_mean、ts_min、ts_sum、where；窗口 ts_min=12、ts_sum=19、ts_mean=40；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #056。
- 源码计算片段：first = _rank(lib.open - _ts_min(lib.open, 12)) second = _rank(_rank(_corr(_ts_sum((lib.high + lib.low) / 2.0, 19), _ts_sum(_ts_mean(lib.volume, 40), 19), 13)) ** 5) return pd.DataFrame(np.where(first < second, 1.0, -1.0), index=lib.close.index, columns=lib.close.columns)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、high、low、open、volume 的滚动相关性、截面排名、滚动均值、滚动最小值、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、high、low、open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动均值、滚动最小值、滚动求和、where 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、low、open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #056。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha056 / 第 677-680 行；总览匹配行 11069
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_061
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：low、volume、滚动相关性、线性衰减、窗口差分、截面排名、动态生成、字段回退
- 计算结构：字段 low、volume；算子 corr、decay_linear、delta、rank、ts_mean、vwap；窗口 decay_linear=12、decay_linear=17、delta=1、ts_mean=80；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #061。
- 源码计算片段：first = _rank(_decay_linear(_delta(lib._vwap(), 1), 12)) second = _rank(_decay_linear(_rank(_corr(lib.low, _ts_mean(lib.volume, 80), 8)), 17)) return -_elementwise_max(first, second)
- 本类中的具体角色：它在“量价背离”总论中具体通过 low、volume 的滚动相关性、线性衰减、窗口差分、截面排名、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、线性衰减、窗口差分、截面排名、滚动均值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #061。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha061 / 第 705-708 行；总览匹配行 11137
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_062
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、volume、滚动相关性、截面排名、动态生成
- 计算结构：字段 high、volume；算子 corr、rank；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #062。
- 源码计算片段：return -_corr(lib.high, _rank(lib.volume), 5)
- 本类中的具体角色：它在“量价背离”总论中具体通过 high、volume 的滚动相关性、截面排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #062。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha062 / 第 711-712 行；总览匹配行 11151
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_064
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、滚动相关性、线性衰减、截面排名、滚动最大值、动态生成、字段回退
- 计算结构：字段 close、volume；算子 corr、decay_linear、rank、ts_max、ts_mean、vwap；窗口 decay_linear=4、decay_linear=14、ts_max=13、ts_mean=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #064。
- 源码计算片段：left = _rank(_decay_linear(_corr(_rank(lib._vwap()), _rank(lib.volume), 4), 4)) right = _rank(_decay_linear(_ts_max(_corr(_rank(lib.close), _rank(_ts_mean(lib.volume, 60)), 4), 13), 14)) return -_elementwise_max(left, right)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、volume 的滚动相关性、线性衰减、截面排名、滚动最大值、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、线性衰减、截面排名、滚动最大值、滚动均值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #064。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha064 / 第 720-723 行；总览匹配行 11176
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_073
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、滚动相关性、线性衰减、截面排名、滚动均值、动态生成、字段回退
- 计算结构：字段 close、volume；算子 corr、decay_linear、rank、ts_mean、ts_rank、vwap；窗口 ts_rank=5、decay_linear=4、decay_linear=3、decay_linear=16、ts_mean=30；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #073。
- 源码计算片段：first = _ts_rank(_decay_linear(_decay_linear(_corr(lib.close, lib.volume, 10), 16), 4), 5) second = _rank(_decay_linear(_corr(lib._vwap(), _ts_mean(lib.volume, 30), 4), 3)) return -(first - second)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、volume 的滚动相关性、线性衰减、截面排名、滚动均值、时间序列排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、线性衰减、截面排名、滚动均值、时间序列排名、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #073。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha073 / 第 768-771 行；总览匹配行 11296
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_074
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：low、volume、滚动相关性、截面排名、滚动均值、滚动求和、动态生成、字段回退
- 计算结构：字段 low、volume；算子 corr、rank、ts_mean、ts_sum、vwap；窗口 ts_sum=20、ts_mean=40；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #074。
- 源码计算片段：first = _rank(_corr(_ts_sum(lib.low * 0.35 + lib._vwap() * 0.65, 20), _ts_sum(_ts_mean(lib.volume, 40), 20), 7)) second = _rank(_corr(_rank(lib._vwap()), _rank(lib.volume), 6)) return first + second
- 本类中的具体角色：它在“量价背离”总论中具体通过 low、volume 的滚动相关性、截面排名、滚动均值、滚动求和、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动均值、滚动求和、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #074。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha074 / 第 774-777 行；总览匹配行 11310
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_077
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、volume、滚动相关性、线性衰减、截面排名、动态生成、字段回退
- 计算结构：字段 high、low、volume；算子 corr、decay_linear、rank、ts_mean、vwap；窗口 decay_linear=20、decay_linear=6、ts_mean=40；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #077。
- 源码计算片段：first = _rank(_decay_linear((lib.high + lib.low) / 2.0 - lib._vwap(), 20)) second = _rank(_decay_linear(_corr((lib.high + lib.low) / 2.0, _ts_mean(lib.volume, 40), 3), 6)) return _elementwise_min(first, second)
- 本类中的具体角色：它在“量价背离”总论中具体通过 high、low、volume 的滚动相关性、线性衰减、截面排名、滚动均值、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 high、low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、线性衰减、截面排名、滚动均值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #077。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha077 / 第 796-799 行；总览匹配行 11356
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_083
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、volume、滚动协方差、截面排名、动态生成
- 计算结构：字段 high、volume；算子 cov、rank；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #083。
- 源码计算片段：return -_rank(_cov(_rank(lib.high), _rank(lib.volume), 5))
- 本类中的具体角色：它在“量价背离”总论中具体通过 high、volume 的滚动协方差、截面排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动协方差、截面排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #083。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha083 / 第 826-827 行；总览匹配行 11434
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_090
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：volume、滚动相关性、截面排名、成交量加权价格、动态生成、字段回退
- 计算结构：字段 volume；算子 corr、rank、vwap；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #090。
- 源码计算片段：return -_rank(_corr(_rank(lib._vwap()), _rank(lib.volume), 5))
- 本类中的具体角色：它在“量价背离”总论中具体通过 volume 的滚动相关性、截面排名、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #090。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha090 / 第 862-863 行；总览匹配行 11526
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_091
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、low、volume、滚动相关性、截面排名、滚动最大值、动态生成
- 计算结构：字段 close、low、volume；算子 corr、rank、ts_max、ts_mean；窗口 ts_mean=40、ts_max=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #091。
- 源码计算片段：return -_rank(lib.close - _ts_max(lib.close, 5)) * _rank(_corr(_ts_mean(lib.volume, 40), lib.low, 5))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、low、volume 的滚动相关性、截面排名、滚动最大值、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动最大值、滚动均值 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #091。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha091 / 第 866-867 行；总览匹配行 11538
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_092
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、abs、滚动相关性、线性衰减、窗口差分、动态生成、字段回退
- 计算结构：字段 close、volume；算子 abs、corr、decay_linear、delta、rank、ts_mean、ts_rank、vwap；窗口 ts_rank=15、decay_linear=3、decay_linear=5、delta=2、ts_mean=180；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #092。
- 源码计算片段：first = _rank(_decay_linear(_delta(lib.close * 0.35 + lib._vwap() * 0.65, 2), 3)) second = _ts_rank(_decay_linear(_corr(_ts_mean(lib.volume, 180), lib.close, 13).abs(), 5), 15) return -_elementwise_max(first, second)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、volume 的abs、滚动相关性、线性衰减、窗口差分、截面排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；abs、滚动相关性、线性衰减、窗口差分、截面排名、滚动均值 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #092。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha092 / 第 870-873 行；总览匹配行 11550
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_099
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、滚动协方差、截面排名、动态生成
- 计算结构：字段 close、volume；算子 cov、rank；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #099。
- 源码计算片段：return -_rank(_cov(_rank(lib.close), _rank(lib.volume), 5))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、volume 的滚动协方差、截面排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动协方差、截面排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #099。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha099 / 第 908-909 行；总览匹配行 10311、11644
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_101
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、volume、滚动相关性、截面排名、滚动均值、动态生成、字段回退
- 计算结构：字段 close、high、volume；算子 corr、rank、ts_mean、ts_sum、vwap、where；窗口 ts_sum=37、ts_mean=30；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #101。
- 源码计算片段：rank1 = _rank(_corr(lib.close, _ts_sum(_ts_mean(lib.volume, 30), 37), 15)) rank2 = _rank(_corr(_rank(lib.high * 0.1 + lib._vwap() * 0.9), _rank(lib.volume), 11)) return pd.DataFrame(np.where(rank1 < rank2, -1.0, 1.0), index=lib.close.index, columns=lib.close.columns)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、high、volume 的滚动相关性、截面排名、滚动均值、滚动求和、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动均值、滚动求和、成交量加权价格、where 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #101。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha101 / 第 916-919 行；总览匹配行 10312、11668
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_104
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、volume、滚动相关性、窗口差分、截面排名、动态生成
- 计算结构：字段 close、high、volume；算子 corr、delta、rank、ts_std；窗口 delta=5、ts_std=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #104。
- 源码计算片段：return -_delta(_corr(lib.high, lib.volume, 5), 5) * _rank(_ts_std(lib.close, 20))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、high、volume 的滚动相关性、窗口差分、截面排名、滚动波动率实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、窗口差分、截面排名、滚动波动率 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #104。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha104 / 第 931-932 行；总览匹配行 11707
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_105
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：open、volume、滚动相关性、截面排名、动态生成
- 计算结构：字段 open、volume；算子 corr、rank；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #105。
- 源码计算片段：return _corr(_rank(lib.open), _rank(lib.volume), 10)
- 本类中的具体角色：它在“量价背离”总论中具体通过 open、volume 的滚动相关性、截面排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #105。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha105 / 第 935-936 行；总览匹配行 11719
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_108
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、volume、滚动相关性、截面排名、保留符号幂、滚动均值、动态生成、字段回退
- 计算结构：字段 high、volume；算子 corr、rank、signed_power、ts_mean、ts_min、vwap；窗口 ts_min=2、ts_mean=120；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #108。
- 源码计算片段：return -_signed_power(_rank(lib.high - _ts_min(lib.high, 2)), _rank(_corr(lib._vwap(), _ts_mean(lib.volume, 120), 6)))
- 本类中的具体角色：它在“量价背离”总论中具体通过 high、volume 的滚动相关性、截面排名、保留符号幂、滚动均值、滚动最小值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、保留符号幂、滚动均值、滚动最小值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #108。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha108 / 第 947-948 行；总览匹配行 11755
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_113
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、滚动相关性、历史滞后、截面排名、滚动求和、动态生成
- 计算结构：字段 close、volume；算子 corr、delay、rank、ts_sum；窗口 ts_sum=5、ts_sum=20、delay=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #113。
- 源码计算片段：return -_rank(_ts_sum(_delay(lib.close, 5), 20) / 20.0) * _corr(lib.close, lib.volume, 2) * _rank(_corr(_ts_sum(lib.close, 5), _ts_sum(lib.close, 20), 2))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、volume 的滚动相关性、历史滞后、截面排名、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、历史滞后、截面排名、滚动求和 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #113。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha113 / 第 976-977 行；总览匹配行 11824
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_115
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、volume、滚动相关性、截面排名、动态生成
- 计算结构：字段 close、high、low、volume；算子 corr、rank、signed_power、ts_mean、ts_rank；窗口 ts_mean=30、ts_rank=4、ts_rank=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #115。
- 源码计算片段：left = _rank(_corr(lib.high * 0.9 + lib.close * 0.1, _ts_mean(lib.volume, 30), 10)) right = _rank(_corr(_ts_rank((lib.high + lib.low) / 2.0, 4), _ts_rank(lib.volume, 10), 7)) return _signed_power(left, right)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、high、low、volume 的滚动相关性、截面排名、保留符号幂、滚动均值、时间序列排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、high、low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、保留符号幂、滚动均值、时间序列排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #115。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha115 / 第 986-989 行；总览匹配行 11850
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_119
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：open、volume、滚动相关性、线性衰减、截面排名、滚动均值、动态生成、字段回退
- 计算结构：字段 open、volume；算子 corr、decay_linear、rank、ts_mean、ts_min、ts_rank、ts_sum、vwap；窗口 decay_linear=7、decay_linear=8、ts_rank=7、ts_sum=26、ts_min=9、ts_mean=5、ts_mean=15；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #119。
- 源码计算片段：first = _rank(_decay_linear(_corr(lib._vwap(), _ts_sum(_ts_mean(lib.volume, 5), 26), 5), 7)) second = _rank(_decay_linear(_ts_rank(_ts_min(_corr(_rank(lib.open), _rank(_ts_mean(lib.volume, 15)), 21), 9), 7), 8)) return first - second
- 本类中的具体角色：它在“量价背离”总论中具体通过 open、volume 的滚动相关性、线性衰减、截面排名、滚动均值、滚动最小值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、线性衰减、截面排名、滚动均值、滚动最小值、时间序列排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #119。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha119 / 第 1004-1007 行；总览匹配行 11900
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_120
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、截面排名、成交量加权价格、动态生成、字段回退
- 计算结构：字段 close；算子 rank、vwap；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #120。
- 源码计算片段：return _safe_divide(_rank(lib._vwap() - lib.close), _rank(lib._vwap() + lib.close))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close 的截面排名、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close 的相对变化或联动，重点观察价格与成交信息是否同步；截面排名、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #120。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha120 / 第 1010-1011 行；总览匹配行 11914
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_121
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：volume、滚动相关性、截面排名、保留符号幂、滚动均值、滚动最小值、动态生成、字段回退
- 计算结构：字段 volume；算子 corr、rank、signed_power、ts_mean、ts_min、ts_rank、vwap；窗口 ts_rank=3、ts_min=12、ts_rank=20、ts_rank=2、ts_mean=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #121。
- 源码计算片段：return -_signed_power(_rank(lib._vwap() - _ts_min(lib._vwap(), 12)), _ts_rank(_corr(_ts_rank(lib._vwap(), 20), _ts_rank(_ts_mean(lib.volume, 60), 2), 18), 3))
- 本类中的具体角色：它在“量价背离”总论中具体通过 volume 的滚动相关性、截面排名、保留符号幂、滚动均值、滚动最小值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、保留符号幂、滚动均值、滚动最小值、时间序列排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #121。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha121 / 第 1014-1015 行；总览匹配行 11926
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_123
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、volume、滚动相关性、截面排名、动态生成
- 计算结构：字段 close、high、low、volume；算子 corr、rank、ts_mean、ts_sum、where；窗口 ts_sum=20、ts_mean=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #123。
- 源码计算片段：left = _rank(_corr(_ts_sum((lib.high + lib.low) / 2.0, 20), _ts_sum(_ts_mean(lib.volume, 60), 20), 9)) right = _rank(_corr(lib.low, lib.volume, 6)) return pd.DataFrame(np.where(left < right, -1.0, 1.0), index=lib.close.index, columns=lib.close.columns)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、high、low、volume 的滚动相关性、截面排名、滚动均值、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、high、low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动均值、滚动求和、where 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #123。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha123 / 第 1023-1026 行；总览匹配行 11951
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_124
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、线性衰减、截面排名、滚动最大值、成交量加权价格、动态生成、字段回退
- 计算结构：字段 close；算子 decay_linear、rank、ts_max、vwap；窗口 decay_linear=2、ts_max=30；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #124。
- 源码计算片段：return _safe_divide(lib.close - lib._vwap(), _decay_linear(_rank(_ts_max(lib.close, 30)), 2))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close 的线性衰减、截面排名、滚动最大值、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close 的相对变化或联动，重点观察价格与成交信息是否同步；线性衰减、截面排名、滚动最大值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #124。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha124 / 第 1029-1030 行；总览匹配行 11965
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_125
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、滚动相关性、线性衰减、窗口差分、截面排名、动态生成、字段回退
- 计算结构：字段 close、volume；算子 corr、decay_linear、delta、rank、ts_mean、vwap；窗口 decay_linear=20、decay_linear=16、delta=3、ts_mean=80；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #125。
- 源码计算片段：numerator = _rank(_decay_linear(_corr(lib._vwap(), _ts_mean(lib.volume, 80), 17), 20)) denominator = _rank(_decay_linear(_delta(lib.close * 0.5 + lib._vwap() * 0.5, 3), 16)) return _safe_divide(numerator, denominator)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、volume 的滚动相关性、线性衰减、窗口差分、截面排名、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、线性衰减、窗口差分、截面排名、滚动均值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #125。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha125 / 第 1033-1036 行；总览匹配行 11977
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_130
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、low、volume、滚动相关性、线性衰减、截面排名、动态生成、字段回退
- 计算结构：字段 high、low、volume；算子 corr、decay_linear、rank、ts_mean、vwap；窗口 decay_linear=10、decay_linear=3、ts_mean=40；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #130。
- 源码计算片段：numerator = _rank(_decay_linear(_corr((lib.high + lib.low) / 2.0, _ts_mean(lib.volume, 40), 9), 10)) denominator = _rank(_decay_linear(_corr(_rank(lib._vwap()), _rank(lib.volume), 7), 3)) return _safe_divide(numerator, denominator)
- 本类中的具体角色：它在“量价背离”总论中具体通过 high、low、volume 的滚动相关性、线性衰减、截面排名、滚动均值、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 high、low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、线性衰减、截面排名、滚动均值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #130。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha130 / 第 1060-1063 行；总览匹配行 12044
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_131
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、滚动相关性、窗口差分、截面排名、保留符号幂、动态生成、字段回退
- 计算结构：字段 close、volume；算子 corr、delta、rank、signed_power、ts_mean、ts_rank、vwap；窗口 ts_rank=18、delta=1、ts_mean=50；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #131。
- 源码计算片段：return _signed_power(_rank(_delta(lib._vwap(), 1)), _ts_rank(_corr(lib.close, _ts_mean(lib.volume, 50), 18), 18))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、volume 的滚动相关性、窗口差分、截面排名、保留符号幂、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、窗口差分、截面排名、保留符号幂、滚动均值、时间序列排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #131。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha131 / 第 1066-1067 行；总览匹配行 12058
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_136
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：open、volume、滚动相关性、窗口差分、截面排名、收益序列、动态生成
- 计算结构：字段 open、volume；算子 corr、delta、rank、returns；窗口 delta=3；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #136。
- 源码计算片段：return -_rank(_delta(lib._returns(), 3)) * _corr(lib.open, lib.volume, 10)
- 本类中的具体角色：它在“量价背离”总论中具体通过 open、volume 的滚动相关性、窗口差分、截面排名、收益序列实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、窗口差分、截面排名、收益序列 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #136。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha136 / 第 1086-1087 行；总览匹配行 12118
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_138
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：low、volume、滚动相关性、线性衰减、窗口差分、截面排名、动态生成、字段回退
- 计算结构：字段 low、volume；算子 corr、decay_linear、delta、rank、ts_mean、ts_rank、vwap；窗口 ts_rank=7、decay_linear=20、decay_linear=16、delta=3、ts_rank=19、ts_rank=8、ts_rank=17、ts_mean=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #138。
- 源码计算片段：first = _rank(_decay_linear(_delta(lib.low * 0.7 + lib._vwap() * 0.3, 3), 20)) second = _ts_rank(_decay_linear(_ts_rank(_corr(_ts_rank(lib.low, 8), _ts_rank(_ts_mean(lib.volume, 60), 17), 5), 19), 16), 7) return -(first - second)
- 本类中的具体角色：它在“量价背离”总论中具体通过 low、volume 的滚动相关性、线性衰减、窗口差分、截面排名、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、线性衰减、窗口差分、截面排名、滚动均值、时间序列排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #138。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha138 / 第 1103-1106 行；总览匹配行 12151
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_139
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：open、volume、滚动相关性、动态生成
- 计算结构：字段 open、volume；算子 corr；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #139。
- 源码计算片段：return -_corr(lib.open, lib.volume, 10)
- 本类中的具体角色：它在“量价背离”总论中具体通过 open、volume 的滚动相关性实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #139。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha139 / 第 1109-1110 行；总览匹配行 12165
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_140
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、open、volume、滚动相关性、动态生成
- 计算结构：字段 close、high、low、open、volume；算子 corr、decay_linear、rank、ts_mean、ts_rank；窗口 ts_rank=3、decay_linear=8、decay_linear=7、ts_rank=8、ts_rank=20、ts_mean=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #140。
- 源码计算片段：left = _rank(_decay_linear((_rank(lib.open) + _rank(lib.low)) - (_rank(lib.high) + _rank(lib.close)), 8)) right = _ts_rank(_decay_linear(_corr(_ts_rank(lib.close, 8), _ts_rank(_ts_mean(lib.volume, 60), 20), 8), 7), 3) return _elementwise_min(left, right)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、high、low、open、volume 的滚动相关性、线性衰减、截面排名、滚动均值、时间序列排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、high、low、open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、线性衰减、截面排名、滚动均值、时间序列排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、low、open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #140。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha140 / 第 1113-1116 行；总览匹配行 12177
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_141
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：high、volume、滚动相关性、截面排名、滚动均值、动态生成
- 计算结构：字段 high、volume；算子 corr、rank、ts_mean；窗口 ts_mean=15；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #141。
- 源码计算片段：return -_rank(_corr(_rank(lib.high), _rank(_ts_mean(lib.volume, 15)), 9))
- 本类中的具体角色：它在“量价背离”总论中具体通过 high、volume 的滚动相关性、截面排名、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动均值 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #141。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha141 / 第 1119-1120 行；总览匹配行 12191
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_142
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、窗口差分、截面排名、滚动均值、时间序列排名、动态生成
- 计算结构：字段 close、volume；算子 delta、rank、ts_mean、ts_rank；窗口 ts_rank=5、delta=1、ts_rank=10、ts_mean=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #142。
- 源码计算片段：return -_rank(_ts_rank(lib.close, 10)) * _rank(_delta(_delta(lib.close, 1), 1)) * _rank(_ts_rank(_safe_divide(lib.volume, _ts_mean(lib.volume, 20)), 5))
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、volume 的窗口差分、截面排名、滚动均值、时间序列排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；窗口差分、截面排名、滚动均值、时间序列排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #142。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha142 / 第 1123-1124 行；总览匹配行 12203
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_148
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、open、volume、滚动相关性、截面排名、滚动均值、动态生成
- 计算结构：字段 close、open、volume；算子 corr、rank、ts_mean、ts_min、ts_sum、where；窗口 ts_sum=9、ts_min=14、ts_mean=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #148。
- 源码计算片段：left = _rank(_corr(lib.open, _ts_sum(_ts_mean(lib.volume, 60), 9), 6)) right = _rank(lib.open - _ts_min(lib.open, 14)) return pd.DataFrame(np.where(left < right, -1.0, 1.0), index=lib.close.index, columns=lib.close.columns)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、open、volume 的滚动相关性、截面排名、滚动均值、滚动最小值、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动均值、滚动最小值、滚动求和、where 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #148。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha148 / 第 1154-1157 行；总览匹配行 12282
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_154
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、滚动相关性、滚动均值、滚动最小值、成交量加权价格、动态生成、字段回退
- 计算结构：字段 close、volume；算子 corr、ts_mean、ts_min、vwap、where；窗口 ts_min=16、ts_mean=180；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #154。
- 源码计算片段：condition = lib._vwap() - _ts_min(lib._vwap(), 16) < _corr(lib._vwap(), _ts_mean(lib.volume, 180), 18) return pd.DataFrame(np.where(condition, 1.0, -1.0), index=lib.close.index, columns=lib.close.columns)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、volume 的滚动相关性、滚动均值、滚动最小值、成交量加权价格、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、滚动均值、滚动最小值、成交量加权价格、where 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #154。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha154 / 第 1188-1190 行；总览匹配行 12364
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_157
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、窗口差分、log、截面排名、收益序列、动态生成
- 计算结构：字段 close；算子 delay、delta、log、rank、returns、ts_min、ts_rank、ts_sum；窗口 ts_min=5、ts_sum=1、ts_rank=5、delta=5、ts_min=2、delay=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #157。
- 源码计算片段：inner = -_rank(_delta(lib.close - 1.0, 5)) nested = _rank(_rank(inner)) nested = np.log(_ts_sum(_ts_min(nested, 2), 1)) nested = _ts_min(_rank(_rank(nested)), 5) return nested + _ts_rank(_delay(-lib._returns(), 6), 5)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close 的历史滞后、窗口差分、log、截面排名、收益序列实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close 的相对变化或联动，重点观察价格与成交信息是否同步；历史滞后、窗口差分、log、截面排名、收益序列、滚动最小值 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #157。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha157 / 第 1207-1212 行；总览匹配行 12407
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_176
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、volume、滚动相关性、截面排名、动态生成
- 计算结构：字段 close、high、low、volume；算子 corr、rank、ts_max、ts_min；窗口 ts_max=12、ts_min=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #176。
- 源码计算片段：spread = _ts_max(lib.high, 12) - _ts_min(lib.low, 12) return _corr(_rank(_safe_divide(lib.close - _ts_min(lib.low, 12), spread)), _rank(lib.volume), 6)
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、high、low、volume 的滚动相关性、截面排名、滚动最大值、滚动最小值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、high、low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动最大值、滚动最小值 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #176。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha176 / 第 1332-1334 行；总览匹配行 12684
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_179
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：low、volume、滚动相关性、截面排名、滚动均值、成交量加权价格、动态生成、字段回退
- 计算结构：字段 low、volume；算子 corr、rank、ts_mean、vwap；窗口 ts_mean=50；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #179。
- 源码计算片段：return _rank(_corr(lib._vwap(), lib.volume, 4)) * _rank(_corr(_rank(lib.low), _rank(_ts_mean(lib.volume, 50)), 12))
- 本类中的具体角色：它在“量价背离”总论中具体通过 low、volume 的滚动相关性、截面排名、滚动均值、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动均值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #179。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha179 / 第 1345-1346 行；总览匹配行 12721
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_191
- 主分类：量价背离
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、high、low、volume、滚动相关性、滚动均值、动态生成
- 计算结构：字段 close、high、low、volume；算子 corr、ts_mean；窗口 ts_mean=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #191。
- 源码计算片段：return _corr(_ts_mean(lib.volume, 20), lib.low, 5) + (lib.high + lib.low) / 2.0 - lib.close
- 本类中的具体角色：它在“量价背离”总论中具体通过 close、high、low、volume 的滚动相关性、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：比较 close、high、low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、滚动均值 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #191。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha191 / 第 1420-1421 行；总览匹配行 7、10300、10312
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha002
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、open、volume、滚动相关性、窗口差分、log、动态生成
- 计算结构：字段 close、open、volume；算子 correlation、delta、log、rank；窗口 correlation=6、delta=2；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：量价排名走势相关性 + 日内涨跌；核心算子：correlation, rank。
- 源码计算片段：return -_correlation( _rank(_delta(np.log(library.volume), 2)), _rank(_safe_divide(library.close - library.open, library.open)), 6, )
- 本类中的具体角色：文章来源把它概括为“量价排名走势相关性 + 日内涨跌”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、窗口差分、log、截面排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #002。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha002 / 第 268-273 行；总览匹配行 8371、8396
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha003
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：open、volume、滚动相关性、截面排名、动态生成
- 计算结构：字段 open、volume；算子 correlation、rank；窗口 correlation=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：开盘价-成交量排名相关性；核心算子：correlation, rank。
- 源码计算片段：return -_correlation(_rank(library.open), _rank(library.volume), 10)
- 本类中的具体角色：文章来源把它概括为“开盘价-成交量排名相关性”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #003。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha003 / 第 276-277 行；总览匹配行 8412
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha006
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：open、volume、滚动相关性、动态生成
- 计算结构：字段 open、volume；算子 correlation；窗口 correlation=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：开盘价与成交量的直接相关性；核心算子：correlation。
- 源码计算片段：return -_correlation(library.open, library.volume, 10)
- 本类中的具体角色：文章来源把它概括为“开盘价与成交量的直接相关性”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #006。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha006 / 第 291-292 行；总览匹配行 8451
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha011
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、volume、窗口差分、截面排名、滚动最大值、滚动最小值、动态生成、字段回退
- 计算结构：字段 close、volume；算子 delta、rank、ts_max、ts_min、vwap；窗口 delta=3、ts_max=3、ts_min=3；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：vwap/close/volume 三者互动；核心算子：rank, correlation, vwap。
- 源码计算片段：vwap_close = _vwap(library) - library.close return ( _rank(_ts_max(vwap_close, 3)) + _rank(_ts_min(vwap_close, 3)) ) * _rank(_delta(library.volume, 3))
- 本类中的具体角色：文章来源把它概括为“vwap/close/volume 三者互动”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；窗口差分、截面排名、滚动最大值、滚动最小值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #011。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha011 / 第 325-329 行；总览匹配行 8353、8525
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha012
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、volume、窗口差分、sign、动态生成
- 计算结构：字段 close、volume；算子 delta、sign；窗口 delta=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：量变方向 × 价变方向；核心算子：sign, delta。
- 源码计算片段：return np.sign(_delta(library.volume, 1)) * -_delta(library.close, 1)
- 本类中的具体角色：文章来源把它概括为“量变方向 × 价变方向”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；窗口差分、sign 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #012。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha012 / 第 332-333 行；总览匹配行 8540
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha013
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、volume、滚动协方差、截面排名、动态生成
- 计算结构：字段 close、volume；算子 covariance、rank；窗口 covariance=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：收盘价与成交量的协方差排名；核心算子：rank, covariance。
- 源码计算片段：return -_rank(_covariance(_rank(library.close), _rank(library.volume), 5))
- 本类中的具体角色：文章来源把它概括为“收盘价与成交量的协方差排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动协方差、截面排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #013。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha013 / 第 336-337 行；总览匹配行 8552
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha014
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：open、volume、滚动相关性、窗口差分、截面排名、收益序列、动态生成
- 计算结构：字段 open、volume；算子 correlation、delta、rank、returns；窗口 correlation=10、delta=3；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：开盘价与收益率的相关性；核心算子：correlation, returns。
- 源码计算片段：return -_rank(_delta(_returns(library), 3)) * _correlation( library.open, library.volume, 10 )
- 本类中的具体角色：文章来源把它概括为“开盘价与收益率的相关性”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 open、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、窗口差分、截面排名、收益序列 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 open、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #014。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha014 / 第 340-343 行；总览匹配行 8564
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha015
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、volume、滚动相关性、截面排名、滚动求和、动态生成
- 计算结构：字段 high、volume；算子 correlation、rank、ts_sum；窗口 correlation=3、ts_sum=3；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：最高价与成交量排名的相关性；核心算子：correlation, rank。
- 源码计算片段：value = _rank( _correlation(_rank(library.high), _rank(library.volume), 3) ) return -_ts_sum(value, 3)
- 本类中的具体角色：文章来源把它概括为“最高价与成交量排名的相关性”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动求和 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #015。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha015 / 第 346-350 行；总览匹配行 8578
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha016
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、volume、滚动协方差、截面排名、动态生成
- 计算结构：字段 high、volume；算子 covariance、rank；窗口 covariance=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：最高价与成交量的协方差排名；核心算子：covariance, rank。
- 源码计算片段：return -_rank(_covariance(_rank(library.high), _rank(library.volume), 5))
- 本类中的具体角色：文章来源把它概括为“最高价与成交量的协方差排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动协方差、截面排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #016。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha016 / 第 353-354 行；总览匹配行 8593
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha017
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、volume、平均成交额/成交量、窗口差分、截面排名、时间序列排名、动态生成、字段回退
- 计算结构：字段 close、volume；算子 adv、delta、rank、ts_rank；窗口 ts_rank=5、delta=1、ts_rank=10、adv=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：收盘价排名与 volume 动量排名；核心算子：rank, ts_rank, delta, volume。
- 源码计算片段：return ( -_rank(_ts_rank(library.close, 10)) * _rank(_delta(_delta(library.close, 1), 1)) * _rank(_ts_rank(_safe_divide(library.volume, _adv(library, 20)), 5)) )
- 本类中的具体角色：文章来源把它概括为“收盘价排名与 volume 动量排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；平均成交额/成交量、窗口差分、截面排名、时间序列排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #017。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha017 / 第 357-362 行；总览匹配行 8605
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha022
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、volume、滚动相关性、窗口差分、截面排名、动态生成
- 计算结构：字段 close、high、volume；算子 correlation、delta、rank、ts_std；窗口 delta=5、ts_std=20、correlation=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：最高价与成交量相关性 + 价格变化；核心算子：correlation, delta, stddev。
- 源码计算片段：return -_delta(_correlation(library.high, library.volume, 5), 5) * _rank( _ts_std(library.close, 20) )
- 本类中的具体角色：文章来源把它概括为“最高价与成交量相关性 + 价格变化”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、窗口差分、截面排名、滚动波动率 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #022。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha022 / 第 399-402 行；总览匹配行 8687
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha025
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、平均成交额/成交量、截面排名、收益序列、成交量加权价格、动态生成、字段回退
- 计算结构：字段 close、high；算子 adv、rank、returns、vwap；窗口 adv=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：收益率 × 成交量偏离 × vwap 排名；核心算子：rank, returns, adv, vwap。
- 源码计算片段：return _rank( -_returns(library) * _adv(library, 20) * _vwap(library) * (library.high - library.close) )
- 本类中的具体角色：文章来源把它概括为“收益率 × 成交量偏离 × vwap 排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、high 的相对变化或联动，重点观察价格与成交信息是否同步；平均成交额/成交量、截面排名、收益序列、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #025。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha025 / 第 423-429 行；总览匹配行 8735
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha026
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、volume、滚动相关性、滚动最大值、时间序列排名、动态生成
- 计算结构：字段 high、volume；算子 correlation、ts_max、ts_rank；窗口 correlation=5、ts_rank=5、ts_max=3；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：时序排名相关性 + 成交量；核心算子：correlation, ts_rank, volume。
- 源码计算片段：value = _correlation( _ts_rank(library.volume, 5), _ts_rank(library.high, 5), 5 ) return -_ts_max(value, 3)
- 本类中的具体角色：文章来源把它概括为“时序排名相关性 + 成交量”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、滚动最大值、时间序列排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #026。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha026 / 第 432-436 行；总览匹配行 8752
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha027
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：volume、条件分支、滚动相关性、截面排名、滚动求和、成交量加权价格、动态生成、字段回退
- 计算结构：字段 volume；算子 conditional、correlation、rank、ts_sum、vwap；窗口 ts_sum=2、correlation=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：量价相关性的排名分位；核心算子：rank, correlation, volume。
- 源码计算片段：value = _rank( _ts_sum( _correlation(_rank(library.volume), _rank(_vwap(library)), 6), 2 ) / 2.0 ) return _conditional(value > 0.5, -1.0, 1.0)
- 本类中的具体角色：文章来源把它概括为“量价相关性的排名分位”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 volume 的相对变化或联动，重点观察价格与成交信息是否同步；条件分支、滚动相关性、截面排名、滚动求和、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #027。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha027 / 第 439-446 行；总览匹配行 8767
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha028
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、平均成交额/成交量、滚动相关性、截面缩放、动态生成、字段回退
- 计算结构：字段 close、high、low；算子 adv、correlation、scale；窗口 correlation=5、adv=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：成交量与均量的相关性；核心算子：correlation, adv, rank。
- 源码计算片段：return _scale( _correlation(_adv(library, 20), library.low, 5) + (library.high + library.low) / 2.0 - library.close )
- 本类中的具体角色：文章来源把它概括为“成交量与均量的相关性”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、high、low 的相对变化或联动，重点观察价格与成交信息是否同步；平均成交额/成交量、滚动相关性、截面缩放 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、low；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #028。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha028 / 第 449-454 行；总览匹配行 8785
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha032
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、滚动相关性、历史滞后、截面缩放、滚动求和、成交量加权价格、动态生成、字段回退
- 计算结构：字段 close；算子 correlation、delay、scale、ts_sum、vwap；窗口 correlation=230、ts_sum=7、delay=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：均值偏离 × 量价相关性衰减；核心算子：scale, correlation。
- 源码计算片段：return _scale(_ts_sum(library.close, 7) / 7.0 - library.close) + 20.0 * _scale( _correlation(_vwap(library), _delay(library.close, 5), 230) )
- 本类中的具体角色：文章来源把它概括为“均值偏离 × 量价相关性衰减”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、历史滞后、截面缩放、滚动求和、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #032。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha032 / 第 493-496 行；总览匹配行 8861
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha040
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、volume、滚动相关性、截面排名、滚动波动率、动态生成
- 计算结构：字段 high、volume；算子 correlation、rank、ts_std；窗口 correlation=10、ts_std=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：高价波动率 × 成交量排名；核心算子：rank, stddev, correlation。
- 源码计算片段：return -_rank(_ts_std(library.high, 10)) * _correlation( library.high, library.volume, 10 )
- 本类中的具体角色：文章来源把它概括为“高价波动率 × 成交量排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动波动率 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #040。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha040 / 第 552-555 行；总览匹配行 8355、8984
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha043
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、volume、平均成交额/成交量、窗口差分、时间序列排名、动态生成、字段回退
- 计算结构：字段 close、volume；算子 adv、delta、ts_rank；窗口 ts_rank=20、ts_rank=8、adv=20、delta=7；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：流动性排名 × 价格变化；核心算子：rank, adv, delta, close。
- 源码计算片段：return _ts_rank(_safe_divide(library.volume, _adv(library, 20)), 20) * _ts_rank( -_delta(library.close, 7), 8 )
- 本类中的具体角色：文章来源把它概括为“流动性排名 × 价格变化”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；平均成交额/成交量、窗口差分、时间序列排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #043。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha043 / 第 567-570 行；总览匹配行 9023
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha044
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、volume、滚动相关性、截面排名、动态生成
- 计算结构：字段 high、volume；算子 correlation、rank；窗口 correlation=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：最低价与成交量排名相关性；核心算子：correlation, rank。
- 源码计算片段：return -_correlation(library.high, _rank(library.volume), 5)
- 本类中的具体角色：文章来源把它概括为“最低价与成交量排名相关性”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #044。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha044 / 第 573-574 行；总览匹配行 9037
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha045
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、volume、滚动相关性、历史滞后、截面排名、滚动求和、动态生成
- 计算结构：字段 close、volume；算子 correlation、delay、rank、ts_sum；窗口 correlation=2、ts_sum=5、ts_sum=20、delay=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：收盘价变化排名 × 量价衰减相关；核心算子：rank, delta, correlation, decay_linear。
- 源码计算片段：return -( _rank(_ts_sum(_delay(library.close, 5), 20) / 20.0) * _correlation(library.close, library.volume, 2) * _rank( _correlation(_ts_sum(library.close, 5), _ts_sum(library.close, 20), 2) ) )
- 本类中的具体角色：文章来源把它概括为“收盘价变化排名 × 量价衰减相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、历史滞后、截面排名、滚动求和 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #045。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha045 / 第 577-584 行；总览匹配行 9049
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha050
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：volume、滚动相关性、截面排名、滚动最大值、成交量加权价格、动态生成、字段回退
- 计算结构：字段 volume；算子 correlation、rank、ts_max、vwap；窗口 ts_max=5、correlation=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：量价排名的时序相关；核心算子：correlation, rank, ts_rank, volume。
- 源码计算片段：return -_ts_max( _rank(_correlation(_rank(library.volume), _rank(_vwap(library)), 5)), 5 )
- 本类中的具体角色：文章来源把它概括为“量价排名的时序相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动最大值、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #050。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha050 / 第 626-629 行；总览匹配行 8356、9138
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha055
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、volume、滚动相关性、截面排名、动态生成
- 计算结构：字段 close、high、low、volume；算子 correlation、rank、ts_max、ts_min；窗口 ts_min=12、ts_max=12、correlation=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：日内振幅与成交量相关；核心算子：correlation, rank, high, low, volume。
- 源码计算片段：low_min = _ts_min(library.low, 12) high_max = _ts_max(library.high, 12) inner = _safe_divide(library.close - low_min, high_max - low_min) return -_correlation(_rank(inner), _rank(library.volume), 6)
- 本类中的具体角色：文章来源把它概括为“日内振幅与成交量相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、high、low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；滚动相关性、截面排名、滚动最大值、滚动最小值 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #055。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha055 / 第 665-669 行；总览匹配行 9217
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha060
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、volume、abs、截面排名、动态生成
- 计算结构：字段 close、high、low、volume；算子 abs、rank、scale、ts_argmax、where；窗口 ts_argmax=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：量价相关性 × 日内涨跌缩放；核心算子：scale, correlation, rank。
- 源码计算片段：denominator = (library.high - library.low).where( (library.high - library.low).abs() > EPSILON, np.nan ) inner = ( ((library.close - library.low) - (library.high - library.close)) / denominator * library.volume ) return -(2.0 * _scale(_rank(inner)) - _scale(_rank(_ts_argmax(library.close, 10))))
- 本类中的具体角色：文章来源把它概括为“量价相关性 × 日内涨跌缩放”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、high、low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；abs、截面排名、截面缩放、窗口极值位置、where 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #060。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha060 / 第 704-713 行；总览匹配行 8357、9296
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha074
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、volume、平均成交额/成交量、滚动相关性、截面排名、动态生成、字段回退
- 计算结构：字段 close、high、volume；算子 adv、correlation、rank、ts_sum、vwap；窗口 correlation=15.1365、correlation=11.4793、ts_sum=37.4843、adv=30；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：收盘价与均量相关排名；核心算子：rank, correlation, close, adv。
- 源码计算片段：vwap = _vwap(library) left = _rank( _correlation(library.close, _ts_sum(_adv(library, 30), 37.4843), 15.1365) ) right = _rank( _correlation( _rank(library.high * 0.0261661 + vwap * (1 - 0.0261661)), _rank(library.volume), 11.4793, ) ) return _bool_signal(left < right, -1.0)
- 本类中的具体角色：文章来源把它概括为“收盘价与均量相关排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、high、volume 的相对变化或联动，重点观察价格与成交信息是否同步；平均成交额/成交量、滚动相关性、截面排名、滚动求和、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；文章分类表标记 IndNeut，但当前源码局部未检测到对应调用，需人工复核
- 索引说明：WorldQuant Formulaic Alpha #074。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha074 / 第 898-910 行；总览匹配行 9602
- 与因子库总览一致性：mentioned
- 语义置信度：中：文章分类与当前实现标记存在差异

### alpha077
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、low、平均成交额/成交量、滚动相关性、线性衰减、截面排名、动态生成、字段回退
- 计算结构：字段 high、low；算子 adv、correlation、decay_linear、rank、vwap；窗口 decay_linear=20.0451、decay_linear=5.64125、correlation=3.1614、adv=40；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：价格变化衰减 × 量价相关；核心算子：rank, decay_linear, delta, correlation。
- 源码计算片段：first = _rank( _decay_linear( (library.high + library.low) / 2.0 + library.high - (_vwap(library) + library.high), 20.0451, ) ) second = _rank( _decay_linear( _correlation((library.high + library.low) / 2.0, _adv(library, 40), 3.1614), 5.64125, ) ) return np.minimum(first, second)
- 本类中的具体角色：文章来源把它概括为“价格变化衰减 × 量价相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 high、low 的相对变化或联动，重点观察价格与成交信息是否同步；平均成交额/成交量、滚动相关性、线性衰减、截面排名、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、low；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #077。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha077 / 第 940-953 行；总览匹配行 9668
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha078
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：low、volume、平均成交额/成交量、滚动相关性、截面排名、保留符号幂、动态生成、字段回退
- 计算结构：字段 low、volume；算子 adv、correlation、rank、signed_power、ts_sum、vwap；窗口 correlation=6.83313、correlation=5.77492、ts_sum=19.7428、adv=40；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：最低价与均量相关排名；核心算子：rank, correlation, low, adv。
- 源码计算片段：vwap = _vwap(library) left = library.low * 0.352233 + vwap * (1 - 0.352233) numerator = _rank( _correlation( _ts_sum(left, 19.7428), _ts_sum(_adv(library, 40), 19.7428), 6.83313, ) ) exponent = _rank( _correlation(_rank(vwap), _rank(library.volume), 5.77492) ) return _signed_power(numerator, exponent)
- 本类中的具体角色：文章来源把它概括为“最低价与均量相关排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；平均成交额/成交量、滚动相关性、截面排名、保留符号幂、滚动求和、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #078。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha078 / 第 956-969 行；总览匹配行 9692
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha081
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：volume、平均成交额/成交量、滚动相关性、log、截面排名、ts_product、动态生成、字段回退
- 计算结构：字段 volume；算子 adv、correlation、log、rank、ts_product、ts_sum、vwap；窗口 correlation=5.07914、correlation=8.47743、ts_product=14.9655、ts_sum=49.6054、adv=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：vwap 与均量的排名相关；核心算子：rank, correlation, vwap, adv。
- 源码计算片段：vwap = _vwap(library) base = _rank( _correlation(vwap, _ts_sum(_adv(library, 10), 49.6054), 8.47743) ) ** 4 left = _rank(np.log(_ts_product(base, 14.9655))) right = _rank(_correlation(_rank(vwap), _rank(library.volume), 5.07914)) return _bool_signal(left < right, -1.0)
- 本类中的具体角色：文章来源把它概括为“vwap 与均量的排名相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 volume 的相对变化或联动，重点观察价格与成交信息是否同步；平均成交额/成交量、滚动相关性、log、截面排名、ts_product、滚动求和 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #081。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha081 / 第 1000-1007 行；总览匹配行 8360、9760
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha085
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、volume、平均成交额/成交量、滚动相关性、动态生成、字段回退
- 计算结构：字段 close、high、low、volume；算子 adv、correlation、rank、signed_power、ts_rank、vwap；窗口 correlation=9.61331、correlation=7.11408、adv=30、ts_rank=3.70596、ts_rank=10.1595；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：最高价排名与均量相关；核心算子：rank, correlation, high, adv。
- 源码计算片段：vwap = _vwap(library) numerator = _rank( _correlation( library.high * 0.876703 + library.close * (1 - 0.876703), _adv(library, 30), 9.61331, ) ) exponent = _rank( _correlation( _ts_rank((library.high + library.low) / 2.0, 3.70596), _ts_rank(library.volume, 10.1595), 7.11408, ) ) return _signed_power(numerator, exponent)
- 本类中的具体角色：文章来源把它概括为“最高价排名与均量相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、high、low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；平均成交额/成交量、滚动相关性、截面排名、保留符号幂、时间序列排名、成交量加权价格 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #085。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha085 / 第 1044-1060 行；总览匹配行 9836
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha088
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、open、平均成交额/成交量、滚动相关性、动态生成、字段回退
- 计算结构：字段 close、high、low、open；算子 adv、correlation、decay_linear、rank、ts_rank；窗口 ts_rank=2.61957、decay_linear=8.06882、decay_linear=6.65053、correlation=8.01266、ts_rank=8.44728、ts_rank=20.6966、adv=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：开盘价排名衰减相关；核心算子：rank, decay_linear, correlation, open。
- 源码计算片段：first = _rank( _decay_linear( _rank(library.open) + _rank(library.low) - _rank(library.high) - _rank(library.close), 8.06882, ) ) second = _ts_rank( _decay_linear( _correlation( _ts_rank(library.close, 8.44728), _ts_rank(_adv(library, 60), 20.6966), 8.01266, ), 6.65053, ), 2.61957, ) return np.minimum(first, second)
- 本类中的具体角色：文章来源把它概括为“开盘价排名衰减相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、high、low、open 的相对变化或联动，重点观察价格与成交信息是否同步；平均成交额/成交量、滚动相关性、线性衰减、截面排名、时间序列排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #088。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha088 / 第 1094-1112 行；总览匹配行 9910
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha092
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、open、平均成交额/成交量、滚动相关性、动态生成、字段回退
- 计算结构：字段 close、high、low、open；算子 adv、correlation、decay_linear、rank、ts_rank；窗口 ts_rank=18.8683、ts_rank=6.80584、decay_linear=14.7221、decay_linear=6.94024、correlation=7.58555、adv=30；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：多维衰减量价信号；核心算子：rank, decay_linear, delta, correlation。
- 源码计算片段：first_condition = ( (library.high + library.low) / 2.0 + library.close ) < (library.low + library.open) first = _ts_rank(_decay_linear(first_condition.astype(float), 14.7221), 18.8683) second = _ts_rank( _decay_linear( _correlation(_rank(library.low), _rank(_adv(library, 30)), 7.58555), 6.94024, ), 6.80584, ) return np.minimum(first, second)
- 本类中的具体角色：文章来源把它概括为“多维衰减量价信号”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 close、high、low、open 的相对变化或联动，重点观察价格与成交信息是否同步；平均成交额/成交量、滚动相关性、线性衰减、截面排名、时间序列排名 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #092。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha092 / 第 1169-1181 行；总览匹配行 10017
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha095
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、low、open、平均成交额/成交量、滚动相关性、截面排名、动态生成、字段回退
- 计算结构：字段 high、low、open；算子 adv、correlation、rank、ts_min、ts_rank、ts_sum；窗口 ts_rank=11.7584、ts_min=12.4105、correlation=12.8742、ts_sum=19.1351、adv=40；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：最高价排名与均量相关；核心算子：rank, correlation, high, adv。
- 源码计算片段：left = _rank(library.open - _ts_min(library.open, 12.4105)) right = _ts_rank( _rank( _correlation( _ts_sum((library.high + library.low) / 2.0, 19.1351), _ts_sum(_adv(library, 40), 19.1351), 12.8742, ) ) ** 5, 11.7584, ) return _bool_signal(left < right)
- 本类中的具体角色：文章来源把它概括为“最高价排名与均量相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 high、low、open 的相对变化或联动，重点观察价格与成交信息是否同步；平均成交额/成交量、滚动相关性、截面排名、滚动最小值、时间序列排名、滚动求和 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、low、open；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #095。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha095 / 第 1221-1234 行；总览匹配行 10093
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha099
- 主分类：量价背离
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：high、low、volume、平均成交额/成交量、滚动相关性、截面排名、动态生成、字段回退
- 计算结构：字段 high、low、volume；算子 adv、correlation、rank、ts_sum；窗口 correlation=8.8136、correlation=6.28259、ts_sum=19.8975、adv=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：最高价与成交量排名相关；核心算子：rank, correlation, high, volume。
- 源码计算片段：left = _rank( _correlation( _ts_sum((library.high + library.low) / 2.0, 19.8975), _ts_sum(_adv(library, 60), 19.8975), 8.8136, ) ) right = _rank(_correlation(library.low, library.volume, 6.28259)) return _bool_signal(left < right, -1.0)
- 本类中的具体角色：文章来源把它概括为“最高价与成交量排名相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：比较 high、low、volume 的相对变化或联动，重点观察价格与成交信息是否同步；平均成交额/成交量、滚动相关性、截面排名、滚动求和 负责把这种关系变成可比较的横截面或时间序列信号。
- 数据依赖与适用场景：依赖 high、low、volume；适合用于价格与成交信息同步性的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #099。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha099 / 第 1321-1330 行；总览匹配行 10225
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

## 波动率

> 因子数量：26；来源分布：alpha_features 15、worldquant_alpha101 11

波动率状态是否切换，以及极端波动之后是否存在回归或延续。这里的重点不是简单判断风险高低，而是定位波动状态在时间窗口中的位置。 低波动可能意味着市场平静，也可能意味着新信息到来前的压缩；高波动可能意味着信息冲击、恐慌或趋势加速。因子通常把波动率与价格方向、极值位置结合，而不是单独使用标准差。

常见表达是 stddev/ts_std、ts_argmax/ts_argmin、correlation、rank 和 decay_linear；先构造收益或价格波动，再观察极值位置或横截面排名。 Alpha#1 的结构是下跌时关注波动率、上涨时使用收盘价，再用 signedpower 放大差异、ts_argmax 定位窗口极值，最后截面排名并中心化。它表达的是“恐慌或波动达到什么位置”，不是波动率越高就必然做空。

Alpha#1 通过条件选择信号源，再判断过去 5 天极值位置；其他波动率因子则把滚动标准差、相关性或极值衰减结合起来。

边界上，波动率对复权价格、缺失值、停牌和极端涨跌幅很敏感。A 股涨跌停会截断真实波动，不能直接照搬美股语境下的波动率解释。

### Alpha158 STD 公式族（5 个参数变体）

这组因子的共同公式是 `close.rolling({window}, min_periods=1).std() / close`。共同输入字段为 close，主要算子为 rolling、std；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“波动率”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_std5、alpha158_std10、alpha158_std20、alpha158_std30、alpha158_std60。

**因子：alpha158_std5**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、标准差、动态生成
- 本条参数差异：沿用上述“Alpha158 STD 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 rolling、std；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 STD5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6977、6983
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_std10**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、标准差、动态生成
- 本条参数差异：沿用上述“Alpha158 STD 公式族”；本因子参数为 window=10。
- 计算结构：字段 close；算子 rolling、std；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 STD10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6987、6993
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_std20**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、标准差、动态生成
- 本条参数差异：沿用上述“Alpha158 STD 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 rolling、std；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 STD20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 6997、7003
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_std30**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、标准差、动态生成
- 本条参数差异：沿用上述“Alpha158 STD 公式族”；本因子参数为 window=30。
- 计算结构：字段 close；算子 rolling、std；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 STD30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7007、7013
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_std60**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、滚动窗口、标准差、动态生成
- 本条参数差异：沿用上述“Alpha158 STD 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 rolling、std；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 STD60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 7017、7023
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 VSTD 公式族（5 个参数变体）

这组因子的共同公式是 `volume.rolling({window}, min_periods=1).std() / volume`。共同输入字段为 volume，主要算子为 rolling、std；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“波动率”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_vstd5、alpha158_vstd10、alpha158_vstd20、alpha158_vstd30、alpha158_vstd60。

**因子：alpha158_vstd5**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、滚动窗口、标准差、动态生成
- 本条参数差异：沿用上述“Alpha158 VSTD 公式族”；本因子参数为 window=5。
- 计算结构：字段 volume；算子 rolling、std；窗口 rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSTD5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8077、8083
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vstd10**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、滚动窗口、标准差、动态生成
- 本条参数差异：沿用上述“Alpha158 VSTD 公式族”；本因子参数为 window=10。
- 计算结构：字段 volume；算子 rolling、std；窗口 rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSTD10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8087、8093
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vstd20**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、滚动窗口、标准差、动态生成
- 本条参数差异：沿用上述“Alpha158 VSTD 公式族”；本因子参数为 window=20。
- 计算结构：字段 volume；算子 rolling、std；窗口 rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSTD20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8097、8103
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vstd30**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、滚动窗口、标准差、动态生成
- 本条参数差异：沿用上述“Alpha158 VSTD 公式族”；本因子参数为 window=30。
- 计算结构：字段 volume；算子 rolling、std；窗口 rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSTD30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8107、8113
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_vstd60**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：volume、滚动窗口、标准差、动态生成
- 本条参数差异：沿用上述“Alpha158 VSTD 公式族”；本因子参数为 window=60。
- 计算结构：字段 volume；算子 rolling、std；窗口 rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 VSTD60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8117、8123
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### Alpha158 WVMA 公式族（5 个参数变体）

这组因子的共同公式是 `rolling(abs(close / close.shift(1) - 1) * volume, {window}).std() / rolling(abs(close / close.shift(1) - 1) * volume, {window}).mean()`。共同输入字段为 close、volume，主要算子为 shift、rolling、std、mean；参数梯度为 window ∈ {5, 10, 20, 30, 60}。

族级解读：window 只改变观察尺度：短窗口反应更快但噪声更大，长窗口更平滑但滞后更强；共同公式才是这组因子的主要经济结构。 当前分类为“波动率”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：alpha158_wvma5、alpha158_wvma10、alpha158_wvma20、alpha158_wvma30、alpha158_wvma60。

**因子：alpha158_wvma5**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、历史位移、滚动窗口、标准差、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 WVMA 公式族”；本因子参数为 window=5。
- 计算结构：字段 close、volume；算子 shift、rolling、std、mean；窗口 shift=1、rolling=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 5；本族最短观察窗口，反应更快但更容易受噪声影响，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 WVMA5。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8127、8133
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_wvma10**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、历史位移、滚动窗口、标准差、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 WVMA 公式族”；本因子参数为 window=10。
- 计算结构：字段 close、volume；算子 shift、rolling、std、mean；窗口 shift=1、rolling=10；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 10；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 WVMA10。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8137、8143
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_wvma20**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、历史位移、滚动窗口、标准差、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 WVMA 公式族”；本因子参数为 window=20。
- 计算结构：字段 close、volume；算子 shift、rolling、std、mean；窗口 shift=1、rolling=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 20；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 WVMA20。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8147、8153
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_wvma30**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、历史位移、滚动窗口、标准差、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 WVMA 公式族”；本因子参数为 window=30。
- 计算结构：字段 close、volume；算子 shift、rolling、std、mean；窗口 shift=1、rolling=30；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 30；处于本族的中间观察尺度，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 WVMA30。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8157、8163
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

**因子：alpha158_wvma60**
- 主分类：波动率
- 因子库来源：alpha_features（Alpha158/Alpha360 模板特征与机器学习输入）
- 辅助标签：close、volume、历史位移、滚动窗口、标准差、均值、动态生成
- 本条参数差异：沿用上述“Alpha158 WVMA 公式族”；本因子参数为 window=60。
- 计算结构：字段 close、volume；算子 shift、rolling、std、mean；窗口 shift=1、rolling=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条只把 window 设为 60；本族较长观察窗口，结果更平滑但滞后更强，经济逻辑仍与公式族一致。
- 数据依赖与限制：依赖 close、volume；由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值。
- 索引说明：Alpha158 WVMA60。
- 来源证据：Factor/libraries/alpha_features.py / _add_alpha158_factors / 第 90-159 行；总览匹配行 8167、8173
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha001
- 主分类：波动率
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、截面排名、收益序列、保留符号幂、窗口极值位置、滚动波动率、动态生成
- 计算结构：字段 close；算子 rank、returns、signed_power、ts_argmax、ts_std、where；窗口 ts_std=20、ts_argmax=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：下跌时看波动率极值位置；核心算子：stddev, ts_argmax。
- 源码计算片段：returns = _returns(library) selected = _ts_std(returns, 20).where(returns < 0, library.close) return _rank(_ts_argmax(_signed_power(selected, 2.0), 5)) - 0.5
- 本类中的具体角色：文章来源把它概括为“下跌时看波动率极值位置”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close；适合用于波动状态和风险暴露的结构解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #001。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha001 / 第 262-265 行；总览匹配行 6、54、8332
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha018
- 主分类：波动率
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、open、abs、滚动相关性、截面排名、滚动波动率、动态生成
- 计算结构：字段 close、open；算子 abs、correlation、rank、ts_std；窗口 correlation=10、ts_std=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：收盘价与开盘价的相关性；核心算子：correlation, stddev。
- 源码计算片段：value = ( _ts_std((library.close - library.open).abs(), 5) + library.close - library.open + _correlation(library.close, library.open, 10) ) return -_rank(value)
- 本类中的具体角色：文章来源把它概括为“收盘价与开盘价的相关性”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、open 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close、open；适合用于波动状态和风险暴露的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #018。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha018 / 第 365-372 行；总览匹配行 8621
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha021
- 主分类：波动率
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、volume、平均成交额/成交量、条件分支、滚动波动率、滚动求和、动态生成、字段回退
- 计算结构：字段 close、volume；算子 adv、conditional、ts_std、ts_sum；窗口 ts_sum=8、ts_sum=2、adv=20、ts_std=8；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：均值偏离 + 成交量条件；核心算子：mean, stddev, close。
- 源码计算片段：mean8 = _ts_sum(library.close, 8) / 8.0 mean2 = _ts_sum(library.close, 2) / 2.0 ratio = _safe_divide(library.volume, _adv(library, 20)) value = _conditional(ratio > 1.0, 1.0, -1.0) value = _conditional(mean2 < mean8 - _ts_std(library.close, 8), 1.0, value) return _conditional(mean8 + _ts_std(library.close, 8) < mean2, -1.0, value)
- 本类中的具体角色：文章来源把它概括为“均值偏离 + 成交量条件”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、volume 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close、volume；适合用于波动状态和风险暴露的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #021。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha021 / 第 390-396 行；总览匹配行 8354、8670
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha034
- 主分类：波动率
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、窗口差分、截面排名、收益序列、滚动波动率、动态生成
- 计算结构：字段 close；算子 delta、rank、returns、ts_std；窗口 delta=1、ts_std=2、ts_std=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：波动率排名与价格反转；核心算子：rank, stddev, delta, close。
- 源码计算片段：return _rank( (1.0 - _rank(_safe_divide(_ts_std(_returns(library), 2), _ts_std(_returns(library), 5)))) + (1.0 - _rank(_delta(library.close, 1))) )
- 本类中的具体角色：文章来源把它概括为“波动率排名与价格反转”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close；适合用于波动状态和风险暴露的结构解释。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #034。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha034 / 第 503-507 行；总览匹配行 8887
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha036
- 主分类：波动率
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、open、volume、abs、平均成交额/成交量、滚动相关性、动态生成、字段回退
- 计算结构：字段 close、open、volume；算子 abs、adv、correlation、delay、rank、returns、ts_rank、ts_sum、vwap；窗口 ts_rank=5、correlation=6、correlation=15、delay=6、adv=20、ts_sum=200、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：多维相关性排名；核心算子：correlation, rank, adv。
- 源码计算片段：return ( 2.21 * _rank(_correlation(library.close - library.open, _delay(library.volume, 1), 15)) + 0.7 * _rank(library.open - library.close) + 0.73 * _rank(_ts_rank(_delay(-_returns(library), 6), 5)) + _rank(_correlation(_vwap(library), _adv(library, 20), 6).abs()) + 0.6 * _rank( (_ts_sum(library.close, 200) / 200.0 - library.open) * (library.close - library.open) ) )
- 本类中的具体角色：文章来源把它概括为“多维相关性排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、open、volume 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close、open、volume；适合用于波动状态和风险暴露的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #036。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha036 / 第 518-530 行；总览匹配行 8918
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha057
- 主分类：波动率
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、线性衰减、截面排名、窗口极值位置、成交量加权价格、动态生成、字段回退
- 计算结构：字段 close；算子 decay_linear、rank、ts_argmax、vwap；窗口 decay_linear=2、ts_argmax=30；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：衰减最低点位置排名；核心算子：decay_linear, rank, ts_argmin, close。
- 源码计算片段：vwap = _vwap(library) return -_safe_divide( library.close - vwap, _decay_linear(_rank(_ts_argmax(library.close, 30)), 2), )
- 本类中的具体角色：文章来源把它概括为“衰减最低点位置排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close；适合用于波动状态和风险暴露的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #057。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha057 / 第 682-687 行；总览匹配行 9250
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha083
- 主分类：波动率
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、high、low、volume、历史滞后、截面排名、动态生成、字段回退
- 计算结构：字段 close、high、low、volume；算子 delay、rank、ts_sum、vwap；窗口 ts_sum=5、delay=2；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：日内振幅的滞后排名；核心算子：rank, delay, high, low。
- 源码计算片段：mean5 = _ts_sum(library.close, 5) / 5.0 numerator = _rank(_rank(library.volume)) * _rank( _delay(_safe_divide(library.high - library.low, mean5), 2) ) denominator = _safe_divide( _safe_divide(library.high - library.low, mean5), _vwap(library) - library.close ) return _safe_divide(numerator, denominator)
- 本类中的具体角色：文章来源把它概括为“日内振幅的滞后排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、high、low、volume 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close、high、low、volume；适合用于波动状态和风险暴露的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #083。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha083 / 第 1026-1034 行；总览匹配行 9802
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha086
- 主分类：波动率
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、open、平均成交额/成交量、滚动相关性、截面排名、时间序列排名、动态生成、字段回退
- 计算结构：字段 close、open；算子 adv、correlation、rank、ts_rank、ts_sum、vwap；窗口 ts_rank=20.4195、correlation=6.00049、ts_sum=14.7444、adv=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：滞后量价相关条件信号；核心算子：rank, correlation, close, adv, delay。
- 源码计算片段：left = _ts_rank( _correlation(library.close, _ts_sum(_adv(library, 20), 14.7444), 6.00049), 20.4195, ) right = _rank((library.open + library.close) - (_vwap(library) + library.open)) return _bool_signal(left < right, -1.0)
- 本类中的具体角色：文章来源把它概括为“滞后量价相关条件信号”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、open 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close、open；适合用于波动状态和风险暴露的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准；文章分类表标记 IndNeut，但当前源码局部未检测到对应调用，需人工复核
- 索引说明：WorldQuant Formulaic Alpha #086。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha086 / 第 1063-1069 行；总览匹配行 9863
- 与因子库总览一致性：mentioned
- 语义置信度：中：文章分类与当前实现标记存在差异

### alpha094
- 主分类：波动率
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：open、high、low、close、volume、平均成交额/成交量、动态生成、字段回退
- 计算结构：字段 open、high、low、close、volume；算子 adv、correlation、rank、signed_power、ts_min、ts_rank、vwap；窗口 ts_rank=2.70756、correlation=18.0926、ts_rank=19.6462、ts_rank=4.02992、adv=60、ts_min=11.5783；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：成交量排名与低位信号；核心算子：rank, correlation, adv。
- 源码计算片段：vwap = _vwap(library) exponent = _ts_rank( _correlation( _ts_rank(vwap, 19.6462), _ts_rank(_adv(library, 60), 4.02992), 18.0926, ), 2.70756, ) return -_signed_power(_rank(vwap - _ts_min(vwap, 11.5783)), exponent)
- 本类中的具体角色：文章来源把它概括为“成交量排名与低位信号”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 open、high、low、close、volume 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 open、high、low、close、volume；适合用于波动状态和风险暴露的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #094。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha094 / 第 1208-1218 行；总览匹配行 10072
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha096
- 主分类：波动率
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：close、volume、平均成交额/成交量、滚动相关性、线性衰减、截面排名、动态生成、字段回退
- 计算结构：字段 close、volume；算子 adv、correlation、decay_linear、rank、ts_argmax、ts_rank、vwap；窗口 ts_rank=8.38151、ts_rank=13.4143、decay_linear=4.16783、decay_linear=14.0365、correlation=3.83878、ts_argmax=12.6556、correlation=3.65459、ts_rank=7.45404、ts_rank=4.13242、adv=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：衰减极值位置 × 量价相关；核心算子：decay_linear, rank, ts_argmax, correlation。
- 源码计算片段：first = _ts_rank( _decay_linear( _correlation(_rank(_vwap(library)), _rank(library.volume), 3.83878), 4.16783, ), 8.38151, ) second = _ts_rank( _decay_linear( _ts_argmax( _correlation( _ts_rank(library.close, 7.45404), _ts_rank(_adv(library, 60), 4.13242), 3.65459, ), 12.6556, ), 14.0365, ), 13.4143, ) return -np.maximum(first, second)
- 本类中的具体角色：文章来源把它概括为“衰减极值位置 × 量价相关”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 close、volume 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close、volume；适合用于波动状态和风险暴露的结构解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #096。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha096 / 第 1237-1259 行；总览匹配行 10117
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

### alpha098
- 主分类：波动率
- 因子库来源：worldquant_alpha101（WorldQuant Formulaic Alpha 101）
- 辅助标签：open、平均成交额/成交量、滚动相关性、线性衰减、截面排名、窗口极值位置、动态生成、字段回退
- 计算结构：字段 open；算子 adv、correlation、decay_linear、rank、ts_argmin、ts_rank、ts_sum、vwap；窗口 decay_linear=7.18088、decay_linear=8.07206、correlation=4.58418、ts_rank=6.95668、ts_sum=26.4719、ts_argmin=8.62571、adv=5、correlation=20.8187、adv=15；滞后 historical_lag_or_rolling
- 公式/实现摘要：文章逻辑：衰减 vwap 相关排名；核心算子：rank, decay_linear, correlation, vwap, adv。
- 源码计算片段：vwap = _vwap(library) first = _rank( _decay_linear( _correlation(vwap, _ts_sum(_adv(library, 5), 26.4719), 4.58418), 7.18088, ) ) second = _rank( _decay_linear( _ts_rank( _ts_argmin( _correlation( _rank(library.open), _rank(_adv(library, 15)), 20.8187, ), 8.62571, ), 6.95668, ), 8.07206, ) ) return first - second
- 本类中的具体角色：文章来源把它概括为“衰减 vwap 相关排名”；源码片段用于确认实际字段、窗口、外层符号和 SVQuant 的字段回退口径。
- 经济直觉：把 open 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 open；适合用于波动状态和风险暴露的结构解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：WorldQuant Formulaic Alpha #098。
- 来源证据：Factor/libraries/worldquant_alpha101.py / _alpha098 / 第 1294-1318 行；总览匹配行 10190
- 与因子库总览一致性：mentioned
- 语义置信度：中高：文章逐因子分类与源码包装器/公式一致

## 波动率与风险分布

> 因子数量：40；来源分布：volatility_lib 23、risk_indicators 12、classic_indicators 3、technical_lib 2

收益分布、回撤、偏度、峰度和尾部状态如何描述风险暴露。它是对 Alpha101 波动率逻辑的扩展，不等同于一个方向性交易信号。 滚动统计把历史收益压缩为风险状态，帮助研究者识别稳定、剧烈、偏斜或尾部事件阶段；大值通常表示某种风险暴露更强，但不自动说明未来收益方向。

常见表达是 rolling std、quantile、skew、kurtosis、drawdown、VaR 或收益分布统计，重点核对窗口、缺失值和收益定义。 方向解释应优先写成风险暴露或状态标签；只有源码明确叠加排名、负号或条件分支时，才进一步讨论相对偏好。

本类主要服务于风险画像和因子组合复核，可与动量、流动性因子交叉查看，但不把风险统计直接当成预测信号。

边界上，风险统计高度依赖收益计算、复权、窗口预热和极端值处理；不同数据源下的同名指标不能默认具有相同口径。

### atr
- 主分类：波动率与风险分布
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：均值、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 mean、rolling；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：真实波幅均值。
- 源码计算片段："""真实波幅均值。""" return self._tr().rolling(window).mean()
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：真实波幅均值。
- 来源证据：Factor/libraries/classic_indicators.py / atr / 第 242-244 行；总览匹配行 608、1839、1841
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### std
- 主分类：波动率与风险分布
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、滚动窗口、标准差
- 计算结构：字段 close；算子 rolling、std；窗口 window=26；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：收盘价总体标准差。
- 源码计算片段："""收盘价总体标准差。""" return self.close.rolling(window).std(ddof=0)
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close 的滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：收盘价总体标准差。
- 来源证据：Factor/libraries/classic_indicators.py / std / 第 283-285 行；总览匹配行 134、134、136
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vstd
- 主分类：波动率与风险分布
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：volume、滚动窗口、标准差
- 计算结构：字段 volume；算子 rolling、std；窗口 window=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：成交量标准差。
- 源码计算片段："""成交量标准差。""" return self.volume.rolling(window).std(ddof=0)
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 volume 的滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 volume 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 volume；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：成交量标准差。
- 来源证据：Factor/libraries/classic_indicators.py / vstd / 第 217-219 行；总览匹配行 650
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### kurtosis120
- 主分类：波动率与风险分布
- 因子库来源：risk_indicators（收益分布与风险统计）
- 辅助标签：收益序列、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 returns、rolling；窗口 rolling=120；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 Kurtosis120：120 日收益率峰度。
- 源码计算片段："""聚宽 Kurtosis120：120 日收益率峰度。""" return self._returns().rolling(120).kurt()
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的收益序列、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 Kurtosis120：120 日收益率峰度。
- 来源证据：Factor/libraries/risk_indicators.py / kurtosis120 / 第 32-34 行；总览匹配行 2474、2482
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### kurtosis20
- 主分类：波动率与风险分布
- 因子库来源：risk_indicators（收益分布与风险统计）
- 辅助标签：收益序列、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 returns、rolling；窗口 rolling=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 Kurtosis20：20 日收益率峰度。
- 源码计算片段："""聚宽 Kurtosis20：20 日收益率峰度。""" return self._returns().rolling(20).kurt()
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的收益序列、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 Kurtosis20：20 日收益率峰度。
- 来源证据：Factor/libraries/risk_indicators.py / kurtosis20 / 第 24-26 行；总览匹配行 2448、2456
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### kurtosis60
- 主分类：波动率与风险分布
- 因子库来源：risk_indicators（收益分布与风险统计）
- 辅助标签：收益序列、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 returns、rolling；窗口 rolling=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 Kurtosis60：60 日收益率峰度。
- 源码计算片段："""聚宽 Kurtosis60：60 日收益率峰度。""" return self._returns().rolling(60).kurt()
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的收益序列、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 Kurtosis60：60 日收益率峰度。
- 来源证据：Factor/libraries/risk_indicators.py / kurtosis60 / 第 28-30 行；总览匹配行 2461、2469
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### skewness120
- 主分类：波动率与风险分布
- 因子库来源：risk_indicators（收益分布与风险统计）
- 辅助标签：收益序列、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 returns、rolling；窗口 rolling=120；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 Skewness120：120 日收益率偏度。
- 源码计算片段："""聚宽 Skewness120：120 日收益率偏度。""" return self._returns().rolling(120).skew()
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的收益序列、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 Skewness120：120 日收益率偏度。
- 来源证据：Factor/libraries/risk_indicators.py / skewness120 / 第 56-58 行；总览匹配行 2552、2560
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### skewness20
- 主分类：波动率与风险分布
- 因子库来源：risk_indicators（收益分布与风险统计）
- 辅助标签：收益序列、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 returns、rolling；窗口 rolling=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 Skewness20：20 日收益率偏度。
- 源码计算片段："""聚宽 Skewness20：20 日收益率偏度。""" return self._returns().rolling(20).skew()
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的收益序列、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 Skewness20：20 日收益率偏度。
- 来源证据：Factor/libraries/risk_indicators.py / skewness20 / 第 48-50 行；总览匹配行 2526、2534
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### skewness60
- 主分类：波动率与风险分布
- 因子库来源：risk_indicators（收益分布与风险统计）
- 辅助标签：收益序列、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 returns、rolling；窗口 rolling=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 Skewness60：60 日收益率偏度。
- 源码计算片段："""聚宽 Skewness60：60 日收益率偏度。""" return self._returns().rolling(60).skew()
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的收益序列、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 Skewness60：60 日收益率偏度。
- 来源证据：Factor/libraries/risk_indicators.py / skewness60 / 第 52-54 行；总览匹配行 2539、2547
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### variance120
- 主分类：波动率与风险分布
- 因子库来源：risk_indicators（收益分布与风险统计）
- 辅助标签：收益序列、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 returns、rolling；窗口 rolling=120；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 Variance120：120 日收益率方差。
- 源码计算片段："""聚宽 Variance120：120 日收益率方差。""" return self._returns().rolling(120).var() * 252
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的收益序列、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 Variance120：120 日收益率方差。
- 来源证据：Factor/libraries/risk_indicators.py / variance120 / 第 68-70 行；总览匹配行 2591、2599
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### variance20
- 主分类：波动率与风险分布
- 因子库来源：risk_indicators（收益分布与风险统计）
- 辅助标签：收益序列、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 returns、rolling；窗口 rolling=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 Variance20：20 日收益率方差。
- 源码计算片段："""聚宽 Variance20：20 日收益率方差。""" return self._returns().rolling(20).var() * 252
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的收益序列、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 Variance20：20 日收益率方差。
- 来源证据：Factor/libraries/risk_indicators.py / variance20 / 第 60-62 行；总览匹配行 2565、2573
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### variance60
- 主分类：波动率与风险分布
- 因子库来源：risk_indicators（收益分布与风险统计）
- 辅助标签：收益序列、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 returns、rolling；窗口 rolling=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 Variance60：60 日收益率方差。
- 源码计算片段："""聚宽 Variance60：60 日收益率方差。""" return self._returns().rolling(60).var() * 252
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的收益序列、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 Variance60：60 日收益率方差。
- 来源证据：Factor/libraries/risk_indicators.py / variance60 / 第 64-66 行；总览匹配行 2578、2586
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### sharpe_ratio_120
- 主分类：波动率与风险分布
- 因子库来源：risk_indicators（收益分布与风险统计）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 sharpe_ratio_120：120 日滚动年化夏普比率。
- 源码计算片段："""聚宽 sharpe_ratio_120：120 日滚动年化夏普比率。""" return self._sharpe(120)
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 sharpe_ratio_120：120 日滚动年化夏普比率。
- 来源证据：Factor/libraries/risk_indicators.py / sharpe_ratio_120 / 第 44-46 行；总览匹配行 2513、2515、2521
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### sharpe_ratio_20
- 主分类：波动率与风险分布
- 因子库来源：risk_indicators（收益分布与风险统计）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 sharpe_ratio_20：20 日滚动年化夏普比率。
- 源码计算片段："""聚宽 sharpe_ratio_20：20 日滚动年化夏普比率。""" return self._sharpe(20)
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 sharpe_ratio_20：20 日滚动年化夏普比率。
- 来源证据：Factor/libraries/risk_indicators.py / sharpe_ratio_20 / 第 36-38 行；总览匹配行 2487、2489、2495
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### sharpe_ratio_60
- 主分类：波动率与风险分布
- 因子库来源：risk_indicators（收益分布与风险统计）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 sharpe_ratio_60：60 日滚动年化夏普比率。
- 源码计算片段："""聚宽 sharpe_ratio_60：60 日滚动年化夏普比率。""" return self._sharpe(60)
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 sharpe_ratio_60：60 日滚动年化夏普比率。
- 来源证据：Factor/libraries/risk_indicators.py / sharpe_ratio_60 / 第 40-42 行；总览匹配行 2500、2502、2508
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### relative_volatility_index
- 主分类：波动率与风险分布
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、diff、ewm、均值、滚动窗口、标准差
- 计算结构：字段 close；算子 diff、ewm、mean、rolling、std、where；窗口 window=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：相对波动指数：按价格方向分配滚动波动率后进行平滑。
- 源码计算片段："""相对波动指数：按价格方向分配滚动波动率后进行平滑。""" volatility = self.close.rolling(window).std(ddof=0) direction = self.close.diff() upside = volatility.where(direction > 0, 0.0) downside = volatility.where(direction < 0, 0.0) upside = upside.ewm(span=smooth, adjust=False).mean() downside = downside.ewm(span=smooth, adjust=False).mean() return 100 * upside / (upside + downside + 1e-10)
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close 的diff、ewm、均值、滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：相对波动指数：按价格方向分配滚动波动率后进行平滑。
- 来源证据：Factor/libraries/technical_lib.py / relative_volatility_index / 第 285-293 行；总览匹配行 1185、1192
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### volume_impact_score
- 主分类：波动率与风险分布
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：amount、close、volume、abs、均值、收益变化、字段回退
- 计算结构：字段 amount、close、volume；算子 abs、mean、pct_change、rolling、where；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：成交额冲击：单位成交额承载的绝对收益滚动均值。
- 源码计算片段："""成交额冲击：单位成交额承载的绝对收益滚动均值。""" window = self._validate_window(window) returns = self.close.pct_change(fill_method=None) if "amount" in self.fields: traded_value = self.amount else: traded_value = self.close.abs() * self.volume traded_value = traded_value.where(traded_value > 0) impact = returns.abs() / traded_value return impact.rolling(window).mean()
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 amount、close、volume 的abs、均值、收益变化、滚动窗口、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 amount、close、volume 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 amount、close、volume；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；滚动窗口前置样本不足时会产生空值
- 索引说明：成交额冲击：单位成交额承载的绝对收益滚动均值。
- 来源证据：Factor/libraries/technical_lib.py / volume_impact_score / 第 434-444 行；总览匹配行 1435、1444
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### atr_percent
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、abs、均值、滚动窗口、where
- 计算结构：字段 close；算子 abs、mean、rolling、where；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：归一化平均真实波幅：ATR / 收盘价绝对值。
- 源码计算片段："""归一化平均真实波幅：ATR / 收盘价绝对值。""" window = self._validate_window(window) true_range = self._true_range() atr = true_range.rolling(window).mean() price = self.close.abs() return atr / price.where(price > 1e-10)
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close 的abs、均值、滚动窗口、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：归一化平均真实波幅：ATR / 收盘价绝对值。
- 来源证据：Factor/libraries/volatility_lib.py / atr_percent / 第 128-134 行；总览匹配行 1827、1835、1856
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### atr_percentile
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：apply、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 apply、rolling；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：ATR 波动状态分位：当前归一化 ATR 在历史窗口中的百分位。
- 源码计算片段："""ATR 波动状态分位：当前归一化 ATR 在历史窗口中的百分位。""" window = self._validate_window(window) rank_window = self._validate_window(rank_window) atr = self.atr_percent(window=window) return atr.rolling(rank_window).apply( self._last_percentile_rank, raw=True, )
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 源码局部未识别字段 的apply、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 源码局部未识别字段 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：ATR 波动状态分位：当前归一化 ATR 在历史窗口中的百分位。
- 来源证据：Factor/libraries/volatility_lib.py / atr_percentile / 第 136-144 行；总览匹配行 1844、1852
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### chaikin_volatility
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：high、low、ewm、均值、历史位移
- 计算结构：字段 high、low；算子 ewm、mean、shift；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：Chaikin 波动率：高低价振幅 EMA 的变动百分比。
- 源码计算片段："""Chaikin 波动率：高低价振幅 EMA 的变动百分比。""" high_low_average = (self.high - self.low).ewm(span=ema_window, adjust=False).mean() return (high_low_average / high_low_average.shift(change_window) - 1) * 100
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 high、low 的ewm、均值、历史位移实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 high、low 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 high、low；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点
- 索引说明：Chaikin 波动率：高低价振幅 EMA 的变动百分比。
- 来源证据：Factor/libraries/volatility_lib.py / chaikin_volatility / 第 117-120 行；总览匹配行 1802、1809
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### downside_vol
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、收益变化、滚动窗口、标准差
- 计算结构：字段 close；算子 pct_change、rolling、std；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：下行波动率：只考虑负收益的波动率。
- 源码计算片段："""下行波动率：只考虑负收益的波动率。""" ret = self.close.pct_change() neg_ret = ret[ret < 0] return neg_ret.rolling(window).std()
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close 的收益变化、滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：下行波动率：只考虑负收益的波动率。
- 来源证据：Factor/libraries/volatility_lib.py / downside_vol / 第 65-69 行；总览匹配行 1690、1698
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### gap
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：open
- 计算结构：字段 open、pre_close；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：跳空：（开盘价 - 前收盘价）/ 前收盘价。
- 源码计算片段："""跳空：（开盘价 - 前收盘价）/ 前收盘价。""" return self.open / self.pre_close - 1
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 open、pre_close 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 open、pre_close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 open、pre_close；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点
- 索引说明：跳空：（开盘价 - 前收盘价）/ 前收盘价。
- 来源证据：Factor/libraries/volatility_lib.py / gap / 第 122-124 行；总览匹配行 1380、1382、1382
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### garman_klass_volatility
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、high、low、open、clip、log
- 计算结构：字段 close、high、low、open；算子 clip、log、mean、rolling、sqrt；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：Garman-Klass 波动率：基于开高低收价格的波动率估计。
- 源码计算片段："""Garman-Klass 波动率：基于开高低收价格的波动率估计。""" high_low = np.log(self.high / self.low) close_open = np.log(self.close / self.open) variance = ( 0.5 * high_low.pow(2) - (2 * np.log(2) - 1) * close_open.pow(2) ).rolling(window).mean() return np.sqrt(variance.clip(lower=0))
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close、high、low、open 的clip、log、均值、滚动窗口、sqrt实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、high、low、open 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：Garman-Klass 波动率：基于开高低收价格的波动率估计。
- 来源证据：Factor/libraries/volatility_lib.py / garman_klass_volatility / 第 100-107 行；总览匹配行 1773、1780
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### high_low_ratio
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：high、low
- 计算结构：字段 high、low；算子 未提取；窗口 window=5；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：高低比：（最高 - 最低）/ 均价。
- 源码计算片段："""高低比：（最高 - 最低）/ 均价。""" avg = (self.high + self.low) / 2 return (self.high - self.low) / (avg + 1e-10)
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 high、low 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 high、low 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 high、low；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点
- 索引说明：高低比：（最高 - 最低）/ 均价。
- 来源证据：Factor/libraries/volatility_lib.py / high_low_ratio / 第 86-89 行；总览匹配行 1734、1742
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### intraday_to_close_vol_ratio
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、high、low、clip、log、均值
- 计算结构：字段 close、high、low；算子 clip、log、mean、rolling、shift、sqrt、std、where；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：日内区间波动与收盘收益波动之比。
- 源码计算片段："""日内区间波动与收盘收益波动之比。""" window = self._validate_window(window) high = self.high.where(self.high > 1e-10) low = self.low.where(self.low > 1e-10) range_log_return = np.log(high / low).replace([np.inf, -np.inf], np.nan) range_volatility = np.sqrt( range_log_return.pow(2).rolling(window).mean().clip(lower=0.0) ) close = self.close.where(self.close > 1e-10) close_log_return = np.log(close / close.shift()).replace( [np.inf, -np.inf], np.nan ) close_volatility = close_log_return.rolling(window).std(ddof=0) return range_vo…
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close、high、low 的clip、log、均值、滚动窗口、历史位移实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、high、low 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close、high、low；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：日内区间波动与收盘收益波动之比。
- 来源证据：Factor/libraries/volatility_lib.py / intraday_to_close_vol_ratio / 第 146-163 行；总览匹配行 1860、1868
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### intraday_volatility
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：high、low、open
- 计算结构：字段 high、low、open；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：日内振幅：（最高 - 最低）/ 开盘价。
- 源码计算片段："""日内振幅：（最高 - 最低）/ 开盘价。""" return (self.high - self.low) / self.open
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 high、low、open 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 high、low、open 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 high、low、open；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点
- 索引说明：日内振幅：（最高 - 最低）/ 开盘价。
- 来源证据：Factor/libraries/volatility_lib.py / intraday_volatility / 第 91-93 行；总览匹配行 1748、1756
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### parkinson_volatility
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：high、low、log、均值、滚动窗口、sqrt
- 计算结构：字段 high、low；算子 log、mean、rolling、sqrt；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：Parkinson 波动率：基于高低价区间的波动率估计。
- 源码计算片段："""Parkinson 波动率：基于高低价区间的波动率估计。""" variance = np.log(self.high / self.low).pow(2).rolling(window).mean() / (4 * np.log(2)) return np.sqrt(variance)
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 high、low 的log、均值、滚动窗口、sqrt实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 high、low 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 high、low；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：Parkinson 波动率：基于高低价区间的波动率估计。
- 来源证据：Factor/libraries/volatility_lib.py / parkinson_volatility / 第 95-98 行；总览匹配行 1761、1768
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### price_range
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、high、low、滚动最大值、滚动最小值、滚动窗口
- 计算结构：字段 close、high、low；算子 max、min、rolling；窗口 window=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：价格区间：（最高 - 最低）/ 收盘价。
- 源码计算片段："""价格区间：（最高 - 最低）/ 收盘价。""" return (self.high.rolling(window).max() - self.low.rolling(window).min()) / self.close
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close、high、low 的滚动最大值、滚动最小值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、high、low 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close、high、low；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：价格区间：（最高 - 最低）/ 收盘价。
- 来源证据：Factor/libraries/volatility_lib.py / price_range / 第 82-84 行；总览匹配行 1052、1054、1055
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### rogers_satchell_volatility
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、high、low、open、clip、log
- 计算结构：字段 close、high、low、open；算子 clip、log、mean、rolling、sqrt；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：Rogers-Satchell 波动率：允许价格存在趋势漂移的 OHLC 估计。
- 源码计算片段："""Rogers-Satchell 波动率：允许价格存在趋势漂移的 OHLC 估计。""" variance = ( np.log(self.high / self.close) * np.log(self.high / self.open) + np.log(self.low / self.close) * np.log(self.low / self.open) ).rolling(window).mean() return np.sqrt(variance.clip(lower=0))
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close、high、low、open 的clip、log、均值、滚动窗口、sqrt实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close、high、low、open 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close、high、low、open；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：含当日 OHLC/VWAP，需明确 A 股收盘后可得性与 T+1 使用时点；滚动窗口前置样本不足时会产生空值
- 索引说明：Rogers-Satchell 波动率：允许价格存在趋势漂移的 OHLC 估计。
- 来源证据：Factor/libraries/volatility_lib.py / rogers_satchell_volatility / 第 109-115 行；总览匹配行 1787、1794
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### tail_loss_concentration
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、apply、收益变化、滚动窗口
- 计算结构：字段 close；算子 apply、pct_change、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：尾部亏损集中度：最差若干负收益占窗口总亏损的比例。
- 源码计算片段：self, window: int = 20, tail_fraction: float = 0.2 ): """尾部亏损集中度：最差若干负收益占窗口总亏损的比例。""" window = self._validate_window(window) tail_fraction = self._validate_tail_fraction(tail_fraction) returns = self.close.pct_change(fill_method=None).replace( [np.inf, -np.inf], np.nan ) return returns.rolling(window).apply( lambda values: self._tail_loss_concentration(values, tail_fraction), raw=True, )
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close 的apply、收益变化、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：尾部亏损集中度：最差若干负收益占窗口总亏损的比例。
- 来源证据：Factor/libraries/volatility_lib.py / tail_loss_concentration / 第 165-177 行；总览匹配行 1885、1893
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### volatility_ratio
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、收益变化、滚动窗口、标准差
- 计算结构：字段 close；算子 pct_change、rolling、std；窗口 short=5、long=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：波动率比：短期波动 / 长期波动。
- 源码计算片段："""波动率比：短期波动 / 长期波动。""" short_vol = self.close.pct_change().rolling(short).std() long_vol = self.close.pct_change().rolling(long).std() return short_vol / (long_vol + 1e-10)
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close 的收益变化、滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：波动率比：短期波动 / 长期波动。
- 来源证据：Factor/libraries/volatility_lib.py / volatility_ratio / 第 42-46 行；总览匹配行 1631、1639
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### volatility_stability
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、收益变化、滚动窗口、标准差
- 计算结构：字段 close；算子 pct_change、rolling、std；窗口 rolling=20、window=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：波动率稳定性：波动率的负波动率。
- 源码计算片段："""波动率稳定性：波动率的负波动率。""" vol = self.close.pct_change().rolling(20).std() return -vol.pct_change().rolling(window).std()
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close 的收益变化、滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：波动率稳定性：波动率的负波动率。
- 来源证据：Factor/libraries/volatility_lib.py / volatility_stability / 第 48-51 行；总览匹配行 1646、1654
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### cvar_5
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、apply、均值、收益变化、分位数、滚动窗口
- 计算结构：字段 close；算子 apply、mean、pct_change、quantile、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：CVaR 5%：条件风险价值（最差 5% 收益的均值）。
- 源码计算片段："""CVaR 5%：条件风险价值（最差 5% 收益的均值）。""" ret = self.close.pct_change() return ret.rolling(window).apply( lambda x: x[x < x.quantile(0.05)].mean(), raw=True )
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close 的apply、均值、收益变化、分位数、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：CVaR 5%：条件风险价值（最差 5% 收益的均值）。
- 来源证据：Factor/libraries/volatility_lib.py / cvar_5 / 第 53-58 行；总览匹配行 1660、1668
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### idiosyncratic_vol_20d
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、均值、收益变化、滚动窗口、标准差
- 计算结构：字段 close；算子 mean、pct_change、rolling、std；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：特异波动率：残差波动率（简化版）。
- 源码计算片段："""特异波动率：残差波动率（简化版）。""" ret = self.close.pct_change() mkt_ret = ret.mean(axis=1) residual = ret.sub(mkt_ret, axis=0) return residual.rolling(window).std()
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close 的均值、收益变化、滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：特异波动率：残差波动率（简化版）。
- 来源证据：Factor/libraries/volatility_lib.py / idiosyncratic_vol_20d / 第 73-78 行；总览匹配行 1705、1713
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### max_drawdown_20d
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、滚动最大值、滚动窗口
- 计算结构：字段 close；算子 max、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：20 日最大回撤。
- 源码计算片段："""20 日最大回撤。""" rolling_max = self.close.rolling(window).max() return (self.close - rolling_max) / rolling_max
- 本类中的具体角色：它在“波动率与风险分布”总论中具体通过 close 的滚动最大值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：把 close 的振幅、离散程度或尾部状态转成风险状态；大值通常表示近期波动或风险暴露更强，但不自动等价于看多或看空。
- 数据依赖与适用场景：依赖 close；适合用于收益分布、回撤和尾部风险解释。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：20 日最大回撤。
- 来源证据：Factor/libraries/volatility_lib.py / max_drawdown_20d / 第 60-63 行；总览匹配行 1676、1684
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### volatility 公式族（5 个参数变体）

这组因子的共同公式是 `self.close.pct_change().rolling(window).std()`。共同输入字段为 close，主要算子为 pct_change、rolling、std；参数梯度为 window ∈ {5, 20, 60, 120, 250}。

族级解读：共同公式对 close 的日收益率做 window 日滚动标准差，成员差异是风险状态的观察周期。 当前分类为“波动率与风险分布”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：volatility_5d、volatility_20d、volatility_60d、volatility_120d、volatility_250d。

**因子：volatility_5d**
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、收益变化、滚动窗口、标准差
- 本条参数差异：沿用上述“volatility 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 pct_change、rolling、std；窗口 window=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=5；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；滚动窗口前置样本不足时会产生空值。
- 索引说明：5 日波动率。
- 来源证据：Factor/libraries/volatility_lib.py / volatility_5d / 第 20-22 行；总览匹配行 1566、1574
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：volatility_20d**
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、收益变化、滚动窗口、标准差
- 本条参数差异：沿用上述“volatility 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 pct_change、rolling、std；窗口 window=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=20；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；滚动窗口前置样本不足时会产生空值。
- 索引说明：20 日波动率。
- 来源证据：Factor/libraries/volatility_lib.py / volatility_20d / 第 24-26 行；总览匹配行 1579、1587
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：volatility_60d**
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、收益变化、滚动窗口、标准差
- 本条参数差异：沿用上述“volatility 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 pct_change、rolling、std；窗口 window=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=60；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；滚动窗口前置样本不足时会产生空值。
- 索引说明：60 日波动率。
- 来源证据：Factor/libraries/volatility_lib.py / volatility_60d / 第 28-30 行；总览匹配行 1592、1600
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：volatility_120d**
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、收益变化、滚动窗口、标准差
- 本条参数差异：沿用上述“volatility 公式族”；本因子参数为 window=120。
- 计算结构：字段 close；算子 pct_change、rolling、std；窗口 window=120；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=120；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；滚动窗口前置样本不足时会产生空值。
- 索引说明：120 日波动率。
- 来源证据：Factor/libraries/volatility_lib.py / volatility_120d / 第 32-34 行；总览匹配行 1605、1613
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：volatility_250d**
- 主分类：波动率与风险分布
- 因子库来源：volatility_lib（波动率、回撤和尾部风险）
- 辅助标签：close、收益变化、滚动窗口、标准差
- 本条参数差异：沿用上述“volatility 公式族”；本因子参数为 window=250。
- 计算结构：字段 close；算子 pct_change、rolling、std；窗口 window=250；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=250；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；滚动窗口前置样本不足时会产生空值。
- 索引说明：250 日波动率（年化）。
- 来源证据：Factor/libraries/volatility_lib.py / volatility_250d / 第 36-38 行；总览匹配行 1618、1626
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

## 价值/估值或规模

> 因子数量：15；来源分布：value_lib 14、alpha_library 1

相对便宜、相对昂贵和公司规模暴露。该类关注横截面相对位置，而不是单个股票的绝对数值。 估值指标可能表达价值回归假设，规模指标可能表达规模溢价或风险暴露；最终方向取决于因子是否取倒数、排名、去极值或与其他信号复合。

常见表达是估值字段、总市值/流通市值、rank、zscore、分位数和中性化；需区分直接字段、数据源推导和缺失回退。 “因子值高”只表示相对估值或规模位置更高，不等于应做多；必须结合原始字段的经济含义和外层符号。

本类因子可作为风格暴露描述，并与 Alpha101 的价格/成交逻辑组合分析；报告重点保留来源、字段和缺失回退。

边界上，基本面和市值字段必须遵守点时可得性，不能用报告期结束后才公开的数据回填历史。

### marketcap
- 主分类：价值/估值或规模
- 因子库来源：alpha_library（历史兼容示例，需区分研究特征与标签）
- 辅助标签：total_mv
- 计算结构：字段 total_mv；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：marketcap
- 源码计算片段：return -self.total_mv
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 total_mv 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 total_mv 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 total_mv；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：marketcap
- 来源证据：Factor/libraries/alpha_library.py / marketcap / 第 27-28 行；总览匹配行 106、114
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### bp
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：无
- 计算结构：字段 pb；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：BP 因子：市净率倒数。
- 源码计算片段："""BP 因子：市净率倒数。""" return 1.0 / self.pb
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 pb 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 pb 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 pb；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：BP 因子：市净率倒数。
- 来源证据：Factor/libraries/value_lib.py / bp / 第 26-28 行；总览匹配行 437、445、487
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### composite_value
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：无
- 计算结构：字段 pb、pe_ttm、ps_ttm；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：综合价值因子：EP + BP + SP 等权合成。
- 源码计算片段："""综合价值因子：EP + BP + SP 等权合成。""" ep = 1.0 / self.pe_ttm bp = 1.0 / self.pb sp = 1.0 / self.ps_ttm return (ep + bp + sp) / 3
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 pb、pe_ttm、ps_ttm 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 pb、pe_ttm、ps_ttm 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 pb、pe_ttm、ps_ttm；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：综合价值因子：EP + BP + SP 等权合成。
- 来源证据：Factor/libraries/value_lib.py / composite_value / 第 40-45 行；总览匹配行 476、484
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### cp_ttm
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：无
- 计算结构：字段 pcf_ttm；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：CP 因子：滚动市现率倒数。
- 源码计算片段："""CP 因子：滚动市现率倒数。""" return 1.0 / self.pcf_ttm
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 pcf_ttm 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 pcf_ttm 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 pcf_ttm；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：CP 因子：滚动市现率倒数。
- 来源证据：Factor/libraries/value_lib.py / cp_ttm / 第 34-36 行；总览匹配行 463、471
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### dividend_cover
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：无
- 计算结构：字段 pe_ttm；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：股息覆盖：净利润 / 分红。
- 源码计算片段："""股息覆盖：净利润 / 分红。""" return self.pe_ttm # 简化
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 pe_ttm 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 pe_ttm 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 pe_ttm；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：股息覆盖：净利润 / 分红。
- 来源证据：Factor/libraries/value_lib.py / dividend_cover / 第 62-64 行；总览匹配行 532、540
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### dividend_yield
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：无
- 计算结构：字段 dividend_yield_ratio；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：股息率。
- 源码计算片段："""股息率。""" return self.dividend_yield if hasattr(self, 'dividend_yield') else self["dividend_yield_ratio"]
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 dividend_yield_ratio 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 dividend_yield_ratio 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 dividend_yield_ratio；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：股息率。
- 来源证据：Factor/libraries/value_lib.py / dividend_yield / 第 58-60 行；总览匹配行 519、527、529
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### earnings_yield
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：均值、标准差
- 计算结构：字段 pe_ttm；算子 mean、std；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：盈利收益率：EP 的 ZSCORE。
- 源码计算片段："""盈利收益率：EP 的 ZSCORE。""" ep = 1.0 / self.pe_ttm return (ep - ep.mean()) / ep.std()
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 pe_ttm 的均值、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 pe_ttm 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 pe_ttm；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：盈利收益率：EP 的 ZSCORE。
- 来源证据：Factor/libraries/value_lib.py / earnings_yield / 第 51-54 行；总览匹配行 505、513
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### ep
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：无
- 计算结构：字段 pe；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：EP 因子：静态市盈率倒数。
- 源码计算片段："""EP 因子：静态市盈率倒数。""" return 1.0 / self.pe
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 pe 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 pe 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 pe；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：EP 因子：静态市盈率倒数。
- 来源证据：Factor/libraries/value_lib.py / ep / 第 22-24 行；总览匹配行 424、432、486
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### ep_ttm
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：无
- 计算结构：字段 pe_ttm；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：EP 因子：滚动市盈率倒数。
- 源码计算片段："""EP 因子：滚动市盈率倒数。""" return 1.0 / self.pe_ttm
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 pe_ttm 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 pe_ttm 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 pe_ttm；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：EP 因子：滚动市盈率倒数。
- 来源证据：Factor/libraries/value_lib.py / ep_ttm / 第 18-20 行；总览匹配行 411、419
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### ev_ebitda
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：无
- 计算结构：字段 pe_ttm；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：EV/EBITDA 倒数。
- 源码计算片段："""EV/EBITDA 倒数。""" return 1.0 / self.pe_ttm
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 pe_ttm 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 pe_ttm 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 pe_ttm；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：EV/EBITDA 倒数。
- 来源证据：Factor/libraries/value_lib.py / ev_ebitda / 第 72-74 行；总览匹配行 558、566
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### ln_cap
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：total_mv、apply、字段回退
- 计算结构：字段 total_mv；算子 apply；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：对数市值。
- 源码计算片段："""对数市值。""" return self.total_mv.apply(lambda x: -x)
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 total_mv 的apply实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 total_mv 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 total_mv；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径
- 索引说明：对数市值。
- 来源证据：Factor/libraries/value_lib.py / ln_cap / 第 78-80 行；总览匹配行 571、579
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### peg
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：无
- 计算结构：字段 pe_ttm；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：PEG：市盈率 / 增长率。
- 源码计算片段："""PEG：市盈率 / 增长率。""" return self.pe_ttm
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 pe_ttm 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 pe_ttm 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 pe_ttm；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：PEG：市盈率 / 增长率。
- 来源证据：Factor/libraries/value_lib.py / peg / 第 68-70 行；总览匹配行 545、553
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### small_size
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：total_mv
- 计算结构：字段 total_mv；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：小市值：负总市值。
- 源码计算片段："""小市值：负总市值。""" return -self.total_mv
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 total_mv 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 total_mv 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 total_mv；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：小市值：负总市值。
- 来源证据：Factor/libraries/value_lib.py / small_size / 第 82-84 行；总览匹配行 584、592
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### sp_ttm
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：无
- 计算结构：字段 ps_ttm；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：SP 因子：滚动市销率倒数。
- 源码计算片段："""SP 因子：滚动市销率倒数。""" return 1.0 / self.ps_ttm
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 ps_ttm 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 ps_ttm 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 ps_ttm；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：SP 因子：滚动市销率倒数。
- 来源证据：Factor/libraries/value_lib.py / sp_ttm / 第 30-32 行；总览匹配行 450、458
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### value_vs_growth
- 主分类：价值/估值或规模
- 因子库来源：value_lib（价值、估值与规模）
- 辅助标签：无
- 计算结构：字段 pe_ttm；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：价值 vs 成长：EP / (1 + 增长率)。
- 源码计算片段："""价值 vs 成长：EP / (1 + 增长率)。""" return 1.0 / self.pe_ttm
- 本类中的具体角色：它在“价值/估值或规模”总论中具体通过 pe_ttm 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：通过 pe_ttm 表达估值、规模或相对便宜程度；最终偏好取决于源码中的符号、排名和组合使用方式。
- 数据依赖与适用场景：依赖 pe_ttm；适合用于估值、规模或相对便宜程度解释。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：价值 vs 成长：EP / (1 + 增长率)。
- 来源证据：Factor/libraries/value_lib.py / value_vs_growth / 第 47-49 行；总览匹配行 492、500
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

## 标签/不可交易

> 因子数量：1；来源分布：alpha_library 1

该类不是交易信号，而是包含未来信息的监督学习目标或事后评价标签。 例如 futureRes 使用未来收盘价变化描述下一时点结果，适合拿来定义标签或检验预测，不应进入当日可交易特征集合。

重点识别 negative shift、lead、future、target 和 forward return 等结构，并记录未来窗口。 标签的正负只表示目标变量方向，不表示因子本身的多空方向。

当前报告将 alpha_library/futureRes 单独标记为标签/不可交易，并保留其 shift(-1) 的源码证据。

边界上，任何新增未来数据迹象都必须进入待复核清单，不能因为名称或总览描述没有提及就忽略。

### futureRes
- 主分类：标签/不可交易
- 因子库来源：alpha_library（历史兼容示例，需区分研究特征与标签）
- 辅助标签：close、历史位移、未来数据
- 计算结构：字段 close；算子 shift；窗口 shift=-1；滞后 future_or_forward
- 公式/实现摘要：索引说明：futureRes
- 源码计算片段：return self.close.shift(-1) - self.close
- 本类中的具体角色：它在本类中承担结果标签角色，而不是可交易输入。
- 经济直觉：该结构含有未来时点数据，适合作为监督学习目标或事后评价标签，不得当作当日可交易输入。
- 数据依赖与适用场景：依赖 close；适合作为监督学习目标或事后评价标签。
- 方向与限制：检测到未来数据迹象，标记为标签/不可交易
- 索引说明：futureRes
- 来源证据：Factor/libraries/alpha_library.py / futureRes / 第 47-48 行；总览匹配行 144、152、12910
- 与因子库总览一致性：mentioned
- 语义置信度：高：未来数据标记直接来自源码结构

## 待复核

> 因子数量：137；来源分布：gtja_alpha191 77、classic_indicators 26、technical_lib 21、technical_indicators 13

当前源码证据不足以稳定映射到前述经济逻辑，先保留为待复核，而不是强行归类。 待补充的通常是字段语义、模板分支、外部数据契约、复合算子拆解或来源描述；该分类本身是证据质量标记。

优先检查函数调用链、字段回退、窗口参数、条件分支、外层符号和总览文档的人工说明。 在结构尚未拆清前不解释多空方向，只报告可确认的输入、算子和限制。

这些条目仍保留独立因子条目和源码证据，后续可以按补齐的字段契约或公式族重新归类。

边界上，待复核不代表无价值，也不代表因子无效，只表示当前语义证据不足。

### bbi
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、均值、滚动窗口、求和
- 计算结构：字段 close；算子 mean、rolling、sum；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：多空指数：四条均线的平均值。
- 源码计算片段："""多空指数：四条均线的平均值。""" return sum(self.close.rolling(n).mean() for n in (short1, short2, long1, long2)) / 4
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口、求和，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：多空指数：四条均线的平均值。
- 来源证据：Factor/libraries/classic_indicators.py / bbi / 第 45-47 行；总览匹配行 609
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### bbiboll
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：均值、滚动窗口
- 计算结构：字段 未从局部源码提取；算子 mean、rolling；窗口 window=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：BBI 多空布林线中轨。
- 源码计算片段："""BBI 多空布林线中轨。""" return self.bbi().rolling(window).mean()
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 源码局部未识别字段 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：BBI 多空布林线中轨。
- 来源证据：Factor/libraries/classic_indicators.py / bbiboll / 第 187-189 行；总览匹配行 610
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### bias
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 window=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：乖离率。
- 源码计算片段："""乖离率。""" average = self.close.rolling(window).mean() return (self.close - average) / average * 100
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：乖离率。
- 来源证据：Factor/libraries/classic_indicators.py / bias / 第 89-92 行；总览匹配行 611
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### boll
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 window=26；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：布林线中轨。
- 源码计算片段："""布林线中轨。""" return self.close.rolling(window).mean()
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：布林线中轨。
- 来源证据：Factor/libraries/classic_indicators.py / boll / 第 191-193 行；总览匹配行 612
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### dbcd
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、均值、滚动窗口、历史位移
- 计算结构：字段 close；算子 mean、rolling、shift；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：异同离差乖离率 DBCD。
- 源码计算片段："""异同离差乖离率 DBCD。""" average = self.close.rolling(bias_window).mean() bias = (self.close - average) / average return self._sma(bias - bias.shift(lag), smooth)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口、历史位移实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口、历史位移，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：异同离差乖离率 DBCD。
- 来源证据：Factor/libraries/classic_indicators.py / dbcd / 第 101-105 行；总览匹配行 617
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### ddi
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：滚动窗口、求和
- 计算结构：字段 未从局部源码提取；算子 rolling、sum；窗口 window=13；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：方向标准差偏离指数 DDI。
- 源码计算片段："""方向标准差偏离指数 DDI。""" dmz, dmf = self._dm() sum_z, sum_f = dmz.rolling(window).sum(), dmf.rolling(window).sum() return (sum_z - sum_f) / (sum_z + sum_f)
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 源码局部未识别字段 和 滚动窗口、求和，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：方向标准差偏离指数 DDI。
- 来源证据：Factor/libraries/classic_indicators.py / ddi / 第 83-87 行；总览匹配行 618
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### dma
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 short=10、long=50；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：平均线差 DDD：短期均线减长期均线。``smooth`` 对应派生线 AMA。
- 源码计算片段："""平均线差 DDD：短期均线减长期均线。``smooth`` 对应派生线 AMA。""" return self.close.rolling(short).mean() - self.close.rolling(long).mean()
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：平均线差 DDD：短期均线减长期均线。``smooth`` 对应派生线 AMA。
- 来源证据：Factor/libraries/classic_indicators.py / dma / 第 49-51 行；总览匹配行 619
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### dpo
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：区间震荡线：收盘价减移动均线。
- 源码计算片段："""区间震荡线：收盘价减移动均线。""" return self.close - self.close.rolling(window // 2 + 1).mean()
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：区间震荡线：收盘价减移动均线。
- 来源证据：Factor/libraries/classic_indicators.py / dpo / 第 107-109 行；总览匹配行 622、993、1000
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### env
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：ENV 指标中轨。
- 源码计算片段："""ENV 指标中轨。""" return self.close.rolling(window).mean()
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：ENV 指标中轨。
- 来源证据：Factor/libraries/classic_indicators.py / env / 第 199-201 行；总览匹配行 623
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### expma
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、ewm、均值
- 计算结构：字段 close；算子 ewm、mean；窗口 window=5；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：指数移动平均。
- 源码计算片段："""指数移动平均。""" return self.close.ewm(span=window, adjust=False).mean()
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 ewm、均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：指数移动平均。
- 来源证据：Factor/libraries/classic_indicators.py / expma / 第 57-59 行；总览匹配行 624
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### keltner_position
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close
- 计算结构：字段 close；算子 未提取；窗口 window=20；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：肯特纳通道位置：收盘价在 EMA/ATR 通道中的归一化位置。
- 源码计算片段：self, window: int = 20, atr_window: int = 10, multiplier: float = 2.0, ): """肯特纳通道位置：收盘价在 EMA/ATR 通道中的归一化位置。""" upper, lower, _ = self._keltner_bands(window, atr_window, multiplier) return (self.close - lower) / (upper - lower + 1e-10)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 若干算术操作，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：肯特纳通道位置：收盘价在 EMA/ATR 通道中的归一化位置。
- 来源证据：Factor/libraries/classic_indicators.py / keltner_position / 第 258-266 行；总览匹配行 626
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### keltner_width
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：abs
- 计算结构：字段 未从局部源码提取；算子 abs；窗口 window=20；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：肯特纳通道宽度：ATR 通道相对 EMA 中轨的幅度。
- 源码计算片段：self, window: int = 20, atr_window: int = 10, multiplier: float = 2.0, ): """肯特纳通道宽度：ATR 通道相对 EMA 中轨的幅度。""" upper, lower, middle = self._keltner_bands(window, atr_window, multiplier) return (upper - lower) / (middle.abs() + 1e-10)
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的abs实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 源码局部未识别字段 和 abs，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：肯特纳通道宽度：ATR 通道相对 EMA 中轨的幅度。
- 来源证据：Factor/libraries/classic_indicators.py / keltner_width / 第 268-276 行；总览匹配行 627
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### ma
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 window=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：简单移动平均。
- 源码计算片段："""简单移动平均。""" return self.close.rolling(window).mean()
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：简单移动平均。
- 来源证据：Factor/libraries/classic_indicators.py / ma / 第 53-55 行；总览匹配行 628、673、674
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### mi
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、历史位移
- 计算结构：字段 close；算子 shift；窗口 window=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：动量指标的 SMA 平滑值。
- 源码计算片段："""动量指标的 SMA 平滑值。""" return self._sma(self.close - self.close.shift(window), window)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史位移实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史位移，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：动量指标的 SMA 平滑值。
- 来源证据：Factor/libraries/classic_indicators.py / mi / 第 229-231 行；总览匹配行 632
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### mtm
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、历史位移
- 计算结构：字段 close；算子 shift；窗口 window=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：动力指标 MTM：收盘价与 N 个交易日前收盘价之差。
- 源码计算片段："""动力指标 MTM：收盘价与 N 个交易日前收盘价之差。""" return self.close - self.close.shift(window)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史位移实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史位移，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：动力指标 MTM：收盘价与 N 个交易日前收盘价之差。
- 来源证据：Factor/libraries/classic_indicators.py / mtm / 第 67-69 行；总览匹配行 633
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### priceosc
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 short=12、long=26；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：价格振荡指标。
- 源码计算片段："""价格振荡指标。""" short_ma = self.close.rolling(short).mean() return (short_ma - self.close.rolling(long).mean()) / short_ma
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：价格振荡指标。
- 来源证据：Factor/libraries/classic_indicators.py / priceosc / 第 71-74 行；总览匹配行 634
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### psy
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、均值、滚动窗口、历史位移
- 计算结构：字段 close；算子 mean、rolling、shift；窗口 window=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：心理指标。
- 源码计算片段："""心理指标。""" return self.close.gt(self.close.shift()).rolling(window).mean() * 100
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口、历史位移实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口、历史位移，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：心理指标。
- 来源证据：Factor/libraries/classic_indicators.py / psy / 第 151-153 行；总览匹配行 635、2780、2788
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### pvt
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、volume、收益变化
- 计算结构：字段 close、volume；算子 pct_change；窗口 源码局部未提取到固定窗口；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：量价趋势指标。
- 源码计算片段："""量价趋势指标。""" return (self.close.pct_change() * self.volume).cumsum()
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的收益变化实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 收益变化，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：量价趋势指标。
- 来源证据：Factor/libraries/classic_indicators.py / pvt / 第 179-181 行；总览匹配行 636
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### rc
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、历史位移
- 计算结构：字段 close；算子 shift；窗口 window=50；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：变化率指数。
- 源码计算片段："""变化率指数。""" return self.close / self.close.shift(window) * 100
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史位移实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史位移，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：变化率指数。
- 来源证据：Factor/libraries/classic_indicators.py / rc / 第 233-235 行；总览匹配行 637
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### srdm
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：均值、滚动窗口、where
- 计算结构：字段 未从局部源码提取；算子 mean、rolling、where；窗口 rolling=10、window=30；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：动向速度比率。
- 源码计算片段："""动向速度比率。""" dmz, dmf = self._dm() z, f = dmz.rolling(10).mean(), dmf.rolling(10).mean() raw = (z - f) / z.where(z > f, f) return self._sma(raw.where((z != 0) | (f != 0), 0.0), window)
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的均值、滚动窗口、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 源码局部未识别字段 和 均值、滚动窗口、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：动向速度比率。
- 来源证据：Factor/libraries/classic_indicators.py / srdm / 第 130-135 行；总览匹配行 640
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### srmi
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、历史位移、where
- 计算结构：字段 close；算子 shift、where；窗口 window=9；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：SRMI 修正指标。
- 源码计算片段："""SRMI 修正指标。""" reference = self.close.shift(window) return (self.close - reference).where(self.close > reference, 0.0) / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史位移、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史位移、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：SRMI 修正指标。
- 来源证据：Factor/libraries/classic_indicators.py / srmi / 第 237-240 行；总览匹配行 641
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### trix
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、ewm、均值、收益变化
- 计算结构：字段 close；算子 ewm、mean、pct_change；窗口 window=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：三重指数平滑平均的日变动率。
- 源码计算片段："""三重指数平滑平均的日变动率。""" triple = self.close.ewm(span=window, adjust=False).mean() triple = triple.ewm(span=window, adjust=False).mean() triple = triple.ewm(span=window, adjust=False).mean() return triple.pct_change() * 100
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的ewm、均值、收益变化实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 ewm、均值、收益变化，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：三重指数平滑平均的日变动率。
- 来源证据：Factor/libraries/classic_indicators.py / trix / 第 76-81 行；总览匹配行 643
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vhf
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、abs、diff、滚动最大值、滚动最小值、滚动窗口
- 计算结构：字段 close；算子 abs、diff、max、min、rolling、sum；窗口 window=28；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：纵横指标。
- 源码计算片段："""纵横指标。""" numerator = self.close.rolling(window).max() - self.close.rolling(window).min() return numerator / self.close.diff().abs().rolling(window).sum()
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、diff、滚动最大值、滚动最小值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、diff、滚动最大值、滚动最小值、滚动窗口、求和，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：纵横指标。
- 来源证据：Factor/libraries/classic_indicators.py / vhf / 第 287-290 行；总览匹配行 644
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vma
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：volume、均值、滚动窗口
- 计算结构：字段 volume；算子 mean、rolling；窗口 window=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：成交量简单移动平均。
- 源码计算片段："""成交量简单移动平均。""" return self.volume.rolling(window).mean()
- 本类中的具体角色：它在“待复核”总论中具体通过 volume 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 volume 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：成交量简单移动平均。
- 来源证据：Factor/libraries/classic_indicators.py / vma / 第 203-205 行；总览匹配行 645
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vosc
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：volume、均值、滚动窗口
- 计算结构：字段 volume；算子 mean、rolling；窗口 short=12、long=26；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：成交量震荡指标。
- 源码计算片段："""成交量震荡指标。""" short_ma = self.volume.rolling(short).mean() return (short_ma - self.volume.rolling(long).mean()) / short_ma * 100
- 本类中的具体角色：它在“待复核”总论中具体通过 volume 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 volume 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：成交量震荡指标。
- 来源证据：Factor/libraries/classic_indicators.py / vosc / 第 212-215 行；总览匹配行 647、3027、3035
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### vr_rate
- 主分类：待复核
- 因子库来源：classic_indicators（经典日线技术、量价与波动指标）
- 辅助标签：close、volume、diff、滚动窗口、求和、where
- 计算结构：字段 close、volume；算子 diff、rolling、sum、where；窗口 window=26；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：成交量比率。
- 源码计算片段："""成交量比率。""" change = self.close.diff() up = self.volume.where(change > 0, 0.0).rolling(window).sum() down = self.volume.where(change < 0, 0.0).rolling(window).sum() flat = self.volume.where(change == 0, 0.0).rolling(window).sum() return (up + flat / 2) / (down + flat / 2) * 100
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的diff、滚动窗口、求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 diff、滚动窗口、求和、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：成交量比率。
- 来源证据：Factor/libraries/classic_indicators.py / vr_rate / 第 155-161 行；总览匹配行 648
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### alpha191_004
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、滚动均值、滚动波动率、where、动态生成
- 计算结构：字段 close、volume；算子 ts_mean、ts_std、where；窗口 ts_mean=8、ts_std=8、ts_mean=2、ts_mean=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #004。
- 源码计算片段：mean_long = _ts_mean(lib.close, 8) std_long = _ts_std(lib.close, 8) mean_short = _ts_mean(lib.close, 2) volume_ratio = _safe_divide(lib.volume, _ts_mean(lib.volume, 20)) condition = (mean_long + std_long < mean_short) condition_mid = mean_short < mean_long - std_long return pd.DataFrame( np.where(condition, -1.0, np.where(condition_mid, 1.0, np.where(volume_ratio >= 1.0, 1.0, -1.0))), index=lib.close.index, columns=lib.close.columns, )
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的滚动均值、滚动波动率、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 滚动均值、滚动波动率、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #004。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha004 / 第 391-402 行；总览匹配行 10367
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_014
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、动态生成
- 计算结构：字段 close；算子 delay；窗口 delay=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #014。
- 源码计算片段：return lib.close - _delay(lib.close, 5)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #014。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha014 / 第 446-447 行；总览匹配行 10502
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_018
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、动态生成
- 计算结构：字段 close；算子 delay；窗口 delay=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #018。
- 源码计算片段：return _safe_divide(lib.close, _delay(lib.close, 5))
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #018。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha018 / 第 462-463 行；总览匹配行 10550
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_019
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、where、动态生成
- 计算结构：字段 close；算子 delay、where；窗口 delay=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #019。
- 源码计算片段：previous = _delay(lib.close, 5) down = lib.close < previous up = lib.close > previous return _safe_divide(lib.close - previous, previous).where(down, _safe_divide(lib.close - previous, lib.close).where(up, 0.0))
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #019。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha019 / 第 466-470 行；总览匹配行 10562
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_020
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、动态生成
- 计算结构：字段 close；算子 delay；窗口 delay=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #020。
- 源码计算片段：previous = _delay(lib.close, 6) return _safe_divide(lib.close - previous, previous) * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #020。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha020 / 第 473-475 行；总览匹配行 10577
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_021
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、滚动均值、动态生成
- 计算结构：字段 close；算子 ts_mean；窗口 ts_mean=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #021。
- 源码计算片段：return _regbeta(_ts_mean(lib.close, 6), np.arange(1, 7, dtype=float), 6)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #021。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha021 / 第 478-479 行；总览匹配行 10590
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_022
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、滚动均值、动态生成
- 计算结构：字段 close；算子 delay、ts_mean；窗口 ts_mean=6、delay=3；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #022。
- 源码计算片段：mean6 = _ts_mean(lib.close, 6) deviation = _safe_divide(lib.close - mean6, mean6) return _sma(deviation - _delay(deviation, 3), 12, 1)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #022。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha022 / 第 482-485 行；总览匹配行 10602
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_023
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、滚动波动率、where、动态生成
- 计算结构：字段 close；算子 delay、ts_std、where；窗口 ts_std=20、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #023。
- 源码计算片段：up = _ts_std(lib.close, 20).where(lib.close > _delay(lib.close, 1), 0.0) down = _ts_std(lib.close, 20).where(lib.close <= _delay(lib.close, 1), 0.0) smooth_up = _sma(up, 20, 1) smooth_down = _sma(down, 20, 1) return 100.0 * _safe_divide(smooth_up, smooth_up + smooth_down)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、滚动波动率、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、滚动波动率、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #023。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha023 / 第 488-493 行；总览匹配行 10616
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_024
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、动态生成
- 计算结构：字段 close；算子 delay；窗口 delay=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #024。
- 源码计算片段：return _sma(lib.close - _delay(lib.close, 5), 5, 1)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #024。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha024 / 第 496-497 行；总览匹配行 10632
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_026
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、滚动相关性、历史滞后、滚动求和、成交量加权价格、动态生成、字段回退
- 计算结构：字段 close；算子 corr、delay、ts_sum、vwap；窗口 delay=5、ts_sum=7；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #026。
- 源码计算片段：return _ts_sum(lib.close, 7) / 7.0 - lib.close + _corr(lib._vwap(), _delay(lib.close, 5), 230)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的滚动相关性、历史滞后、滚动求和、成交量加权价格实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 滚动相关性、历史滞后、滚动求和、成交量加权价格，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：源码存在 VWAP/ADV/市值或字段回退，需记录实际数据口径；由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #026。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha026 / 第 504-505 行；总览匹配行 10656
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_027
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、动态生成
- 计算结构：字段 close；算子 delay；窗口 delay=3、delay=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #027。
- 源码计算片段：momentum = _safe_divide(lib.close - _delay(lib.close, 3), _delay(lib.close, 3)) * 100.0 + _safe_divide(lib.close - _delay(lib.close, 6), _delay(lib.close, 6)) * 100.0 return _wma(momentum, 12)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #027。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha027 / 第 508-510 行；总览匹配行 10668
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_029
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、历史滞后、动态生成
- 计算结构：字段 close、volume；算子 delay；窗口 delay=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #029。
- 源码计算片段：return _safe_divide(lib.close - _delay(lib.close, 6), _delay(lib.close, 6)) * lib.volume
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #029。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha029 / 第 521-522 行；总览匹配行 10697
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_030
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：open、high、low、close、volume、动态生成
- 计算结构：字段 open、high、low、close、volume；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #030。
- 源码计算片段：# 原始公式需要 Fama-French 市场因子；当前面板没有该数据时返回缺失值。 return None
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 open、high、low、close、volume 和 若干算术操作，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 open、high、low、close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #030。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha030 / 第 525-527 行；总览匹配行 10709
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_031
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、滚动均值、动态生成
- 计算结构：字段 close；算子 ts_mean；窗口 ts_mean=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #031。
- 源码计算片段：mean12 = _ts_mean(lib.close, 12) return _safe_divide(lib.close - mean12, mean12) * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #031。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha031 / 第 530-532 行；总览匹配行 10722
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_034
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、滚动均值、动态生成
- 计算结构：字段 close；算子 ts_mean；窗口 ts_mean=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #034。
- 源码计算片段：return _safe_divide(_ts_mean(lib.close, 12), lib.close)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #034。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha034 / 第 544-545 行；总览匹配行 10760
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_040
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 close、volume；算子 delay、ts_sum、where；窗口 delay=1、ts_sum=26；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #040。
- 源码计算片段：up = lib.volume.where(lib.close > _delay(lib.close, 1), 0.0) down = lib.volume.where(lib.close <= _delay(lib.close, 1), 0.0) return _safe_divide(_ts_sum(up, 26), _ts_sum(down, 26)) * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 历史滞后、滚动求和、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #040。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha040 / 第 573-576 行；总览匹配行 10837
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_043
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 close、volume；算子 delay、ts_sum、where；窗口 delay=1、ts_sum=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #043。
- 源码计算片段：previous = _delay(lib.close, 1) signed_volume = lib.volume.where(lib.close > previous, (-lib.volume).where(lib.close < previous, 0.0)) return _ts_sum(signed_volume, 6)
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 历史滞后、滚动求和、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #043。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha043 / 第 587-590 行；总览匹配行 10875
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_046
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、滚动均值、动态生成
- 计算结构：字段 close；算子 ts_mean；窗口 ts_mean=24、ts_mean=12、ts_mean=3、ts_mean=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #046。
- 源码计算片段：return (_ts_mean(lib.close, 3) + _ts_mean(lib.close, 6) + _ts_mean(lib.close, 12) + _ts_mean(lib.close, 24)) / (4.0 * lib.close)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #046。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha046 / 第 601-602 行；总览匹配行 10913
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_053
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、动态生成
- 计算结构：字段 close；算子 delay；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #053。
- 源码计算片段：return _count(lib.close > _delay(lib.close, 1), 12) / 12.0 * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #053。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha053 / 第 651-652 行；总览匹配行 11019
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_058
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、动态生成
- 计算结构：字段 close；算子 delay；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #058。
- 源码计算片段：return _count(lib.close > _delay(lib.close, 1), 20) / 20.0 * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #058。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha058 / 第 689-690 行；总览匹配行 11097
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_063
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、abs、历史滞后、动态生成
- 计算结构：字段 close；算子 abs、delay；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #063。
- 源码计算片段：change = lib.close - _delay(lib.close, 1) return _safe_divide(_sma(_elementwise_max(change, 0.0), 6, 1), _sma(change.abs(), 6, 1)) * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #063。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha063 / 第 715-717 行；总览匹配行 11163
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_065
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、滚动均值、动态生成
- 计算结构：字段 close；算子 ts_mean；窗口 ts_mean=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #065。
- 源码计算片段：return _safe_divide(_ts_mean(lib.close, 6), lib.close)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #065。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha065 / 第 726-727 行；总览匹配行 11190
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_066
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、滚动均值、动态生成
- 计算结构：字段 close；算子 ts_mean；窗口 ts_mean=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #066。
- 源码计算片段：mean6 = _ts_mean(lib.close, 6) return _safe_divide(lib.close - mean6, mean6) * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #066。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha066 / 第 730-732 行；总览匹配行 11202
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_067
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、abs、历史滞后、动态生成
- 计算结构：字段 close；算子 abs、delay；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #067。
- 源码计算片段：change = lib.close - _delay(lib.close, 1) return _safe_divide(_sma(_elementwise_max(change, 0.0), 24, 1), _sma(change.abs(), 24, 1)) * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #067。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha067 / 第 735-737 行；总览匹配行 11215
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_070
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：open、high、low、close、volume、滚动波动率、动态生成
- 计算结构：字段 open、high、low、close、volume；算子 ts_std；窗口 ts_std=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #070。
- 源码计算片段：return _ts_std(lib._amount(), 6)
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的滚动波动率实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 open、high、low、close、volume 和 滚动波动率，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 open、high、low、close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #070。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha070 / 第 754-755 行；总览匹配行 11258
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_071
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、滚动均值、动态生成
- 计算结构：字段 close；算子 ts_mean；窗口 ts_mean=24；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #071。
- 源码计算片段：mean24 = _ts_mean(lib.close, 24) return _safe_divide(lib.close - mean24, mean24) * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #071。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha071 / 第 758-760 行；总览匹配行 11270
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_076
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、abs、历史滞后、滚动均值、滚动波动率、动态生成
- 计算结构：字段 close、volume；算子 abs、delay、ts_mean、ts_std；窗口 ts_std=20、ts_mean=20、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #076。
- 源码计算片段：scaled = _safe_divide((lib.close / _delay(lib.close, 1) - 1.0).abs(), lib.volume) return _safe_divide(_ts_std(scaled, 20), _ts_mean(scaled, 20))
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的abs、历史滞后、滚动均值、滚动波动率实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 abs、历史滞后、滚动均值、滚动波动率，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #076。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha076 / 第 791-793 行；总览匹配行 11343
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_079
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、abs、历史滞后、动态生成
- 计算结构：字段 close；算子 abs、delay；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #079。
- 源码计算片段：change = lib.close - _delay(lib.close, 1) return _safe_divide(_sma(_elementwise_max(change, 0.0), 12, 1), _sma(change.abs(), 12, 1)) * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #079。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha079 / 第 808-810 行；总览匹配行 11384
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_080
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：volume、历史滞后、动态生成
- 计算结构：字段 volume；算子 delay；窗口 delay=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #080。
- 源码计算片段：return _safe_divide(lib.volume - _delay(lib.volume, 5), _delay(lib.volume, 5)) * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 volume 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 volume 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #080。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha080 / 第 813-814 行；总览匹配行 11397
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_081
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：volume、动态生成
- 计算结构：字段 volume；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #081。
- 源码计算片段：return _sma(lib.volume, 21, 2)
- 本类中的具体角色：它在“待复核”总论中具体通过 volume 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 volume 和 若干算术操作，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #081。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha081 / 第 817-818 行；总览匹配行 11409
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_084
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 close、volume；算子 delay、ts_sum、where；窗口 delay=1、ts_sum=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #084。
- 源码计算片段：previous = _delay(lib.close, 1) signed = lib.volume.where(lib.close > previous, (-lib.volume).where(lib.close < previous, 0.0)) return _ts_sum(signed, 20)
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 历史滞后、滚动求和、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #084。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha084 / 第 830-833 行；总览匹配行 11446
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_085
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、窗口差分、滚动均值、时间序列排名、动态生成
- 计算结构：字段 close、volume；算子 delta、ts_mean、ts_rank；窗口 ts_rank=20、ts_rank=8、ts_mean=20、delta=7；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #085。
- 源码计算片段：return _ts_rank(_safe_divide(lib.volume, _ts_mean(lib.volume, 20)), 20) * _ts_rank(-_delta(lib.close, 7), 8)
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的窗口差分、滚动均值、时间序列排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 窗口差分、滚动均值、时间序列排名，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #085。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha085 / 第 836-837 行；总览匹配行 11460
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_086
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、where、动态生成
- 计算结构：字段 close；算子 delay、where；窗口 delay=20、delay=10、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #086。
- 源码计算片段：value = _safe_divide(_delay(lib.close, 20) - _delay(lib.close, 10), 10.0) - _safe_divide(_delay(lib.close, 10) - lib.close, 10.0) return pd.DataFrame(np.where(value > 0.25, -1.0, np.where(value < 0.0, 1.0, -(lib.close - _delay(lib.close, 1)))), index=lib.close.index, columns=lib.close.columns)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #086。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha086 / 第 840-842 行；总览匹配行 11472
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_088
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、动态生成
- 计算结构：字段 close；算子 delay；窗口 delay=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #088。
- 源码计算片段：return _safe_divide(lib.close - _delay(lib.close, 20), _delay(lib.close, 20))
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #088。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha088 / 第 851-852 行；总览匹配行 11499
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_089
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、动态生成
- 计算结构：字段 close；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #089。
- 源码计算片段：fast = _sma(lib.close, 13, 2) slow = _sma(lib.close, 27, 2) diff = fast - slow return 2.0 * (diff - _sma(diff, 10, 2))
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 若干算术操作，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #089。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha089 / 第 855-859 行；总览匹配行 11511
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_094
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 close、volume；算子 delay、ts_sum、where；窗口 delay=1、ts_sum=30；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #094。
- 源码计算片段：previous = _delay(lib.close, 1) signed = lib.volume.where(lib.close > previous, (-lib.volume).where(lib.close < previous, 0.0)) return _ts_sum(signed, 30)
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 历史滞后、滚动求和、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #094。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha094 / 第 882-885 行；总览匹配行 11578
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_095
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：open、high、low、close、volume、滚动波动率、动态生成
- 计算结构：字段 open、high、low、close、volume；算子 ts_std；窗口 ts_std=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #095。
- 源码计算片段：return _ts_std(lib._amount(), 20)
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的滚动波动率实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 open、high、low、close、volume 和 滚动波动率，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 open、high、low、close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #095。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha095 / 第 888-889 行；总览匹配行 11592
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_097
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：volume、滚动波动率、动态生成
- 计算结构：字段 volume；算子 ts_std；窗口 ts_std=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #097。
- 源码计算片段：return _ts_std(lib.volume, 10)
- 本类中的具体角色：它在“待复核”总论中具体通过 volume 的滚动波动率实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 volume 和 滚动波动率，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #097。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha097 / 第 898-899 行；总览匹配行 11618
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_098
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、窗口差分、滚动均值、滚动最小值、where、动态生成
- 计算结构：字段 close；算子 delay、delta、ts_mean、ts_min、where；窗口 ts_mean=100、delta=100、delay=100、delta=3、ts_min=100；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #098。
- 源码计算片段：mean100 = _ts_mean(lib.close, 100) condition = _safe_divide(_delta(mean100, 100), _delay(lib.close, 100)) <= 0.05 return (-(lib.close - _ts_min(lib.close, 100))).where(condition, -_delta(lib.close, 3))
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、窗口差分、滚动均值、滚动最小值、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、窗口差分、滚动均值、滚动最小值、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #098。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha098 / 第 902-905 行；总览匹配行 11630
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_100
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：volume、滚动波动率、动态生成
- 计算结构：字段 volume；算子 ts_std；窗口 ts_std=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #100。
- 源码计算片段：return _ts_std(lib.volume, 20)
- 本类中的具体角色：它在“待复核”总论中具体通过 volume 的滚动波动率实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 volume 和 滚动波动率，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #100。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha100 / 第 912-913 行；总览匹配行 10312、11656
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_102
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：volume、abs、历史滞后、动态生成
- 计算结构：字段 volume；算子 abs、delay；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #102。
- 源码计算片段：change = lib.volume - _delay(lib.volume, 1) return _safe_divide(_sma(_elementwise_max(change, 0.0), 6, 1), _sma(change.abs(), 6, 1)) * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 volume 的abs、历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 volume 和 abs、历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #102。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha102 / 第 922-924 行；总览匹配行 11682
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_106
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、动态生成
- 计算结构：字段 close；算子 delay；窗口 delay=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #106。
- 源码计算片段：return lib.close - _delay(lib.close, 20)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #106。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha106 / 第 939-940 行；总览匹配行 11731
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_112
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、abs、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 close；算子 abs、delay、ts_sum、where；窗口 ts_sum=12、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #112。
- 源码计算片段：change = lib.close - _delay(lib.close, 1) up = change.where(change > 0, 0.0) down = change.abs().where(change < 0, 0.0) up_sum = _ts_sum(up, 12) down_sum = _ts_sum(down, 12) return _safe_divide(up_sum - down_sum, up_sum + down_sum) * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、历史滞后、滚动求和、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #112。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha112 / 第 967-973 行；总览匹配行 11807
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_116
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、动态生成
- 计算结构：字段 close；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #116。
- 源码计算片段：return _regbeta(lib.close, np.arange(1, 21, dtype=float), 20)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 若干算术操作，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #116。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha116 / 第 992-993 行；总览匹配行 11864
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_122
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、log、动态生成
- 计算结构：字段 close；算子 delay、log；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #122。
- 源码计算片段：triple = _sma(_sma(_sma(np.log(lib.close), 13, 2), 13, 2), 13, 2) return _safe_divide(triple - _delay(triple, 1), _delay(triple, 1))
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、log实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、log，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #122。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha122 / 第 1018-1020 行；总览匹配行 11938
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_127
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、abs、滚动最大值、动态生成
- 计算结构：字段 close；算子 abs、ts_max；窗口 ts_max=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #127。
- 源码计算片段：return (_safe_divide(100.0 * (lib.close - _ts_max(lib.close, 12)), _ts_max(lib.close, 12))).abs()
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、滚动最大值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、滚动最大值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #127。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha127 / 第 1043-1044 行；总览匹配行 12003
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_129
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、abs、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 close；算子 abs、delay、ts_sum、where；窗口 ts_sum=12、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #129。
- 源码计算片段：change = lib.close - _delay(lib.close, 1) return _ts_sum(change.abs().where(change < 0, 0.0), 12)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、历史滞后、滚动求和、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #129。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha129 / 第 1055-1057 行；总览匹配行 12031
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_132
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：open、high、low、close、volume、滚动均值、动态生成
- 计算结构：字段 open、high、low、close、volume；算子 ts_mean；窗口 ts_mean=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #132。
- 源码计算片段：return _ts_mean(lib._amount(), 20)
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 open、high、low、close、volume 和 滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 open、high、low、close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #132。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha132 / 第 1070-1071 行；总览匹配行 12070
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_134
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、历史滞后、动态生成
- 计算结构：字段 close、volume；算子 delay；窗口 delay=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #134。
- 源码计算片段：return _safe_divide(lib.close - _delay(lib.close, 12), _delay(lib.close, 12)) * lib.volume
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #134。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha134 / 第 1078-1079 行；总览匹配行 12094
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_135
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、动态生成
- 计算结构：字段 close；算子 delay；窗口 delay=1、delay=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #135。
- 源码计算片段：return _sma(_delay(_safe_divide(lib.close, _delay(lib.close, 20)), 1), 20, 1)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #135。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha135 / 第 1082-1083 行；总览匹配行 12106
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_143
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、where、动态生成
- 计算结构：字段 close；算子 delay、where；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #143。
- 源码计算片段：previous = _delay(lib.close, 1) growth = _safe_divide(lib.close - previous, previous) return growth.where((lib.close > previous) & growth.notna(), 1.0).cumprod()
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #143。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha143 / 第 1127-1130 行；总览匹配行 12215
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_144
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、abs、历史滞后、动态生成
- 计算结构：字段 close；算子 abs、delay；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #144。
- 源码计算片段：down = lib.close < _delay(lib.close, 1) part = _safe_divide((lib.close / _delay(lib.close, 1) - 1.0).abs(), lib._amount()) return _safe_divide(_sumif(part, 20, down), _count(down, 20))
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #144。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha144 / 第 1133-1136 行；总览匹配行 12229
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_145
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：volume、滚动均值、动态生成
- 计算结构：字段 volume；算子 ts_mean；窗口 ts_mean=12、ts_mean=9、ts_mean=26；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #145。
- 源码计算片段：return _safe_divide(_ts_mean(lib.volume, 9) - _ts_mean(lib.volume, 26), _ts_mean(lib.volume, 12)) * 100.0
- 本类中的具体角色：它在“待复核”总论中具体通过 volume 的滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 volume 和 滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #145。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha145 / 第 1139-1140 行；总览匹配行 12243
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_146
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、滚动均值、动态生成
- 计算结构：字段 close；算子 delay、ts_mean；窗口 delay=1、ts_mean=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #146。
- 源码计算片段：returns = _safe_divide(lib.close - _delay(lib.close, 1), _delay(lib.close, 1)) deviation = returns - _sma(returns, 61, 2) denominator = _sma(deviation ** 2, 61, 2) return _safe_divide(_ts_mean(deviation, 20) * deviation, denominator)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #146。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha146 / 第 1143-1147 行；总览匹配行 12255
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_147
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、滚动均值、动态生成
- 计算结构：字段 close；算子 ts_mean；窗口 ts_mean=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #147。
- 源码计算片段：return _regbeta(_ts_mean(lib.close, 12), np.arange(1, 13, dtype=float), 12)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #147。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha147 / 第 1150-1151 行；总览匹配行 12270
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_149
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、收益变化、收益序列、历史位移、where、动态生成
- 计算结构：字段 close；算子 pct_change、returns、shift、where；窗口 shift=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #149。
- 源码计算片段：benchmark_close, _ = lib._benchmark() benchmark_return = benchmark_close.pct_change() down_market = benchmark_close < benchmark_close.shift(1) stock_return = lib._returns().where(down_market, axis=0) market_return = benchmark_return.where(down_market) market_panel = pd.DataFrame(np.broadcast_to(market_return.to_numpy()[:, None], lib.close.shape), index=lib.close.index, columns=lib.close.columns) return _regbeta(stock_return, market_panel, 252)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的收益变化、收益序列、历史位移、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 收益变化、收益序列、历史位移、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #149。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha149 / 第 1160-1167 行；总览匹配行 12296
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_151
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、动态生成
- 计算结构：字段 close；算子 delay；窗口 delay=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #151。
- 源码计算片段：return _sma(lib.close - _delay(lib.close, 20), 20, 1)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #151。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha151 / 第 1174-1175 行；总览匹配行 12326
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_152
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、滚动均值、动态生成
- 计算结构：字段 close；算子 delay、ts_mean；窗口 delay=1、ts_mean=12、ts_mean=26、delay=9；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #152。
- 源码计算片段：inner = _sma(_delay(_safe_divide(lib.close, _delay(lib.close, 9)), 1), 9, 1) delayed = _delay(inner, 1) return _sma(_ts_mean(delayed, 12) - _ts_mean(delayed, 26), 9, 1)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #152。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha152 / 第 1178-1181 行；总览匹配行 12338
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_153
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、滚动均值、动态生成
- 计算结构：字段 close；算子 ts_mean；窗口 ts_mean=24、ts_mean=12、ts_mean=3、ts_mean=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #153。
- 源码计算片段：return (_ts_mean(lib.close, 3) + _ts_mean(lib.close, 6) + _ts_mean(lib.close, 12) + _ts_mean(lib.close, 24)) / 4.0
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #153。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha153 / 第 1184-1185 行；总览匹配行 12352
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_155
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：volume、动态生成
- 计算结构：字段 volume；算子 未提取；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #155。
- 源码计算片段：fast = _sma(lib.volume, 13, 2) slow = _sma(lib.volume, 27, 2) diff = fast - slow return diff - _sma(diff, 10, 2)
- 本类中的具体角色：它在“待复核”总论中具体通过 volume 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 volume 和 若干算术操作，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #155。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha155 / 第 1193-1197 行；总览匹配行 12377
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_160
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、滚动波动率、where、动态生成
- 计算结构：字段 close；算子 delay、ts_std、where；窗口 ts_std=20、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #160。
- 源码计算片段：return _sma(_ts_std(lib.close, 20).where(lib.close <= _delay(lib.close, 1), 0.0), 20, 1)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、滚动波动率、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、滚动波动率、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #160。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha160 / 第 1229-1230 行；总览匹配行 12453
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_162
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、abs、历史滞后、滚动最大值、滚动最小值、动态生成
- 计算结构：字段 close；算子 abs、delay、ts_max、ts_min；窗口 delay=1、ts_min=12、ts_max=12；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #162。
- 源码计算片段：change = lib.close - _delay(lib.close, 1) rsi = _safe_divide(_sma(_elementwise_max(change, 0.0), 12, 1), _sma(change.abs(), 12, 1)) * 100.0 return _safe_divide(rsi - _ts_min(rsi, 12), _ts_max(rsi, 12) - _ts_min(rsi, 12))
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、历史滞后、滚动最大值、滚动最小值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、历史滞后、滚动最大值、滚动最小值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #162。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha162 / 第 1239-1242 行；总览匹配行 12479
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_165
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、滚动均值、滚动波动率、滚动求和、动态生成
- 计算结构：字段 close；算子 ts_mean、ts_std、ts_sum；窗口 ts_sum=48、ts_std=48、ts_mean=48；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #165。
- 源码计算片段：x = _ts_sum(lib.close - _ts_mean(lib.close, 48), 48) maximum = _row_max(x) minimum = _row_min(x) std = _ts_std(lib.close, 48) return -_safe_divide(x.sub(maximum, axis=0), std).add(minimum, axis=0)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的滚动均值、滚动波动率、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 滚动均值、滚动波动率、滚动求和，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #165。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha165 / 第 1257-1262 行；总览匹配行 12521
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_166
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、滚动均值、滚动求和、动态生成
- 计算结构：字段 close；算子 delay、ts_mean、ts_sum；窗口 ts_sum=20、delay=1、ts_mean=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #166。
- 源码计算片段：returns = _safe_divide(lib.close, _delay(lib.close, 1)) - 1.0 p1 = -20.0 * (20.0 - 1.0) ** 1.5 * _ts_sum(returns - _ts_mean(returns, 20), 20) p2 = (20.0 - 1.0) * (20.0 - 2.0) * _ts_sum((_ts_mean(_safe_divide(lib.close, _delay(lib.close, 1)), 20)) ** 2, 20) ** 1.5 return _safe_divide(p1, p2)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、滚动均值、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、滚动均值、滚动求和，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #166。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha166 / 第 1265-1269 行；总览匹配行 12537
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_167
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、滚动求和、where、动态生成
- 计算结构：字段 close；算子 delay、ts_sum、where；窗口 ts_sum=12、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #167。
- 源码计算片段：change = (lib.close - _delay(lib.close, 1)).where(lib.close > _delay(lib.close, 1), 0.0) return _ts_sum(change, 12)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、滚动求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、滚动求和、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #167。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha167 / 第 1272-1274 行；总览匹配行 12552
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_168
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：volume、滚动均值、动态生成
- 计算结构：字段 volume；算子 ts_mean；窗口 ts_mean=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #168。
- 源码计算片段：return -_safe_divide(lib.volume, _ts_mean(lib.volume, 20))
- 本类中的具体角色：它在“待复核”总论中具体通过 volume 的滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 volume 和 滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #168。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha168 / 第 1277-1278 行；总览匹配行 12565
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_169
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、滚动均值、动态生成
- 计算结构：字段 close；算子 delay、ts_mean；窗口 delay=1、ts_mean=12、ts_mean=26；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #169。
- 源码计算片段：inner = _sma(lib.close - _delay(lib.close, 1), 9, 1) delayed = _delay(inner, 1) return _sma(_ts_mean(delayed, 12) - _ts_mean(delayed, 26), 10, 1)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #169。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha169 / 第 1281-1284 行；总览匹配行 12577
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_172
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：open、high、low、close、volume、abs、动态生成
- 计算结构：字段 open、high、low、close、volume；算子 abs、ts_mean、ts_sum；窗口 ts_sum=14、ts_mean=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #172。
- 源码计算片段：true_range, dm_plus, dm_minus = _directional_movement(lib) scale = _ts_sum(true_range, 14) plus = _safe_divide(_ts_sum(dm_plus, 14) * 100.0, scale) minus = _safe_divide(_ts_sum(dm_minus, 14) * 100.0, scale) return _ts_mean(_safe_divide((minus - plus).abs(), plus + minus) * 100.0, 6)
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的abs、滚动均值、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 open、high、low、close、volume 和 abs、滚动均值、滚动求和，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 open、high、low、close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #172。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha172 / 第 1307-1312 行；总览匹配行 12627
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_173
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、log、动态生成
- 计算结构：字段 close；算子 log；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #173。
- 源码计算片段：first = _sma(lib.close, 13, 2) second = _sma(first, 13, 2) third = _sma(_sma(_sma(np.log(lib.close), 13, 2), 13, 2), 13, 2) return 3.0 * first - 2.0 * second + third
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的log实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 log，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #173。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha173 / 第 1315-1319 行；总览匹配行 12643
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_174
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、滚动波动率、where、动态生成
- 计算结构：字段 close；算子 delay、ts_std、where；窗口 ts_std=20、delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #174。
- 源码计算片段：return _sma(_ts_std(lib.close, 20).where(lib.close >= _delay(lib.close, 1), 0.0), 20, 1)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、滚动波动率、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、滚动波动率、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #174。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha174 / 第 1322-1323 行；总览匹配行 12658
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_178
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、历史滞后、动态生成
- 计算结构：字段 close、volume；算子 delay；窗口 delay=1；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #178。
- 源码计算片段：return _safe_divide(lib.close - _delay(lib.close, 1), _delay(lib.close, 1)) * lib.volume
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的历史滞后实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 历史滞后，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #178。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha178 / 第 1341-1342 行；总览匹配行 12709
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_180
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、volume、abs、窗口差分、sign、滚动均值、动态生成
- 计算结构：字段 close、volume；算子 abs、delta、sign、ts_mean、ts_rank、where；窗口 delta=7、ts_rank=60、ts_mean=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #180。
- 源码计算片段：change = _delta(lib.close, 7) signal = -_ts_rank(change.abs(), 60) * np.sign(change) return signal.where(_ts_mean(lib.volume, 20) < lib.volume, -lib.volume)
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的abs、窗口差分、sign、滚动均值、时间序列排名实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 abs、窗口差分、sign、滚动均值、时间序列排名、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #180。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha180 / 第 1349-1352 行；总览匹配行 12733
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_181
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、abs、均值、收益序列、滚动窗口、滚动均值、动态生成
- 计算结构：字段 close；算子 abs、mean、returns、rolling、ts_mean、ts_sum；窗口 ts_sum=20、rolling=20、ts_mean=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #181。
- 源码计算片段：benchmark_close, _ = lib._benchmark() returns = lib._returns() benchmark_deviation = benchmark_close - benchmark_close.rolling(20, min_periods=20).mean() deviation_panel = _broadcast_series(benchmark_deviation, lib.close) numerator = _ts_sum(returns - _ts_mean(returns, 20) - deviation_panel.pow(2), 20) denominator = _ts_sum(deviation_panel.abs().pow(3), 20) return _safe_divide(numerator, denominator)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、均值、收益序列、滚动窗口、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、均值、收益序列、滚动窗口、滚动均值、滚动求和，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准；滚动窗口前置样本不足时会产生空值
- 索引说明：国泰君安 Alpha191 #181。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha181 / 第 1355-1362 行；总览匹配行 12747
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_183
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、滚动均值、滚动波动率、滚动求和、动态生成
- 计算结构：字段 close；算子 ts_mean、ts_std、ts_sum；窗口 ts_sum=24、ts_mean=24、ts_std=24；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #183。
- 源码计算片段：x = _ts_sum(lib.close - _ts_mean(lib.close, 24), 24) return -_safe_divide(x.sub(_row_max(x), axis=0), _ts_std(lib.close, 24)).add(_row_min(x), axis=0)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的滚动均值、滚动波动率、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 滚动均值、滚动波动率、滚动求和，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #183。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha183 / 第 1371-1373 行；总览匹配行 12779
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_186
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：open、high、low、close、volume、abs、动态生成
- 计算结构：字段 open、high、low、close、volume；算子 abs、delay、ts_mean、ts_sum；窗口 ts_sum=14、ts_mean=6、delay=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #186。
- 源码计算片段：true_range, dm_plus, dm_minus = _directional_movement(lib) scale = _ts_sum(true_range, 14) plus = _safe_divide(_ts_sum(dm_plus, 14) * 100.0, scale) minus = _safe_divide(_ts_sum(dm_minus, 14) * 100.0, scale) adx = _ts_mean(_safe_divide((minus - plus).abs(), plus + minus) * 100.0, 6) return (adx + _delay(adx, 6)) / 2.0
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的abs、历史滞后、滚动均值、滚动求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 open、high、low、close、volume 和 abs、历史滞后、滚动均值、滚动求和，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 open、high、low、close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #186。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha186 / 第 1384-1390 行；总览匹配行 12816
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_189
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、abs、滚动均值、动态生成
- 计算结构：字段 close；算子 abs、ts_mean；窗口 ts_mean=6；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #189。
- 源码计算片段：return _ts_mean((lib.close - _ts_mean(lib.close, 6)).abs(), 6)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、滚动均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、滚动均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #189。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha189 / 第 1404-1405 行；总览匹配行 12860
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### alpha191_190
- 主分类：待复核
- 因子库来源：gtja_alpha191（国泰君安 Alpha191 公式复算）
- 辅助标签：close、历史滞后、log、where、动态生成
- 计算结构：字段 close；算子 delay、log、where；窗口 delay=1、delay=19；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：国泰君安 Alpha191 #190。
- 源码计算片段：returns = _safe_divide(lib.close, _delay(lib.close, 1)) - 1.0 threshold = _safe_divide(lib.close, _delay(lib.close, 19)) ** (1.0 / 20.0) - 1.0 squared_error = (returns - threshold) ** 2 up = returns > threshold down = returns < threshold numerator = (_count(up, 20) - 1.0) * _sumif(squared_error, 20, down) denominator = _count(down, 20) * _sumif(squared_error, 20, up) ratio = _safe_divide(numerator, denominator).where(lambda frame: frame > 0) return np.log(ratio)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的历史滞后、log、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 历史滞后、log、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：由动态模板或包装器注册，具体窗口/字段以生成参数为准
- 索引说明：国泰君安 Alpha191 #190。
- 来源证据：Factor/libraries/gtja_alpha191.py / _alpha190 / 第 1408-1417 行；总览匹配行 12872
- 与因子库总览一致性：mentioned
- 语义置信度：中：共享模板可解释，需结合具体参数复核

### boll_down
- 主分类：待复核
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、均值、滚动窗口、标准差
- 计算结构：字段 close；算子 mean、rolling、std；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：20 日布林线下轨。
- 源码计算片段："""20 日布林线下轨。""" middle = self.close.rolling(window).mean() return (middle - n_std * self.close.rolling(window).std()) / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口、标准差，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：20 日布林线下轨。
- 来源证据：Factor/libraries/technical_indicators.py / boll_down / 第 13-16 行；总览匹配行 2222、2230
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### boll_up
- 主分类：待复核
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、均值、滚动窗口、标准差
- 计算结构：字段 close；算子 mean、rolling、std；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：20 日布林线上轨。
- 源码计算片段："""20 日布林线上轨。""" middle = self.close.rolling(window).mean() return (middle + n_std * self.close.rolling(window).std()) / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口、标准差，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：20 日布林线上轨。
- 来源证据：Factor/libraries/technical_indicators.py / boll_up / 第 18-21 行；总览匹配行 2236、2244
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### ema5
- 主分类：待复核
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、ewm、均值
- 计算结构：字段 close；算子 ewm、mean；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：5 日指数移动均线。
- 源码计算片段："""5 日指数移动均线。""" return self.close.ewm(span=5, adjust=False).mean() / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 ewm、均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：5 日指数移动均线。
- 来源证据：Factor/libraries/technical_indicators.py / ema5 / 第 23-25 行；总览匹配行 2250、2258
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### emac10
- 主分类：待复核
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、ewm、均值
- 计算结构：字段 close；算子 ewm、mean；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 EMAC10：10 日收盘价指数移动均线。
- 源码计算片段："""聚宽 EMAC10：10 日收盘价指数移动均线。""" return self.close.ewm(span=10, adjust=False).mean() / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 ewm、均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 EMAC10：10 日收盘价指数移动均线。
- 来源证据：Factor/libraries/technical_indicators.py / emac10 / 第 27-29 行；总览匹配行 2263、2271
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### emac12
- 主分类：待复核
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、ewm、均值
- 计算结构：字段 close；算子 ewm、mean；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 EMAC12：12 日收盘价指数移动均线。
- 源码计算片段："""聚宽 EMAC12：12 日收盘价指数移动均线。""" return self.close.ewm(span=12, adjust=False).mean() / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 ewm、均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 EMAC12：12 日收盘价指数移动均线。
- 来源证据：Factor/libraries/technical_indicators.py / emac12 / 第 31-33 行；总览匹配行 2276、2284
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### emac120
- 主分类：待复核
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、ewm、均值
- 计算结构：字段 close；算子 ewm、mean；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 EMAC120：120 日收盘价指数移动均线。
- 源码计算片段："""聚宽 EMAC120：120 日收盘价指数移动均线。""" return self.close.ewm(span=120, adjust=False).mean() / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 ewm、均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 EMAC120：120 日收盘价指数移动均线。
- 来源证据：Factor/libraries/technical_indicators.py / emac120 / 第 43-45 行；总览匹配行 2315、2323
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### emac20
- 主分类：待复核
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、ewm、均值
- 计算结构：字段 close；算子 ewm、mean；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 EMAC20：20 日收盘价指数移动均线。
- 源码计算片段："""聚宽 EMAC20：20 日收盘价指数移动均线。""" return self.close.ewm(span=20, adjust=False).mean() / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 ewm、均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 EMAC20：20 日收盘价指数移动均线。
- 来源证据：Factor/libraries/technical_indicators.py / emac20 / 第 35-37 行；总览匹配行 2289、2297
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### emac26
- 主分类：待复核
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、ewm、均值
- 计算结构：字段 close；算子 ewm、mean；窗口 源码局部未提取到固定窗口；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：聚宽 EMAC26：26 日收盘价指数移动均线。
- 源码计算片段："""聚宽 EMAC26：26 日收盘价指数移动均线。""" return self.close.ewm(span=26, adjust=False).mean() / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 ewm、均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：聚宽 EMAC26：26 日收盘价指数移动均线。
- 来源证据：Factor/libraries/technical_indicators.py / emac26 / 第 39-41 行；总览匹配行 2302、2310
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### mac10
- 主分类：待复核
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 rolling=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 MAC10：10 日移动均线。
- 源码计算片段："""聚宽 MAC10：10 日移动均线。""" return self.close.rolling(10).mean() / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 MAC10：10 日移动均线。
- 来源证据：Factor/libraries/technical_indicators.py / mac10 / 第 51-53 行；总览匹配行 2341、2349
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### mac120
- 主分类：待复核
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 rolling=120；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 MAC120：120 日移动均线。
- 源码计算片段："""聚宽 MAC120：120 日移动均线。""" return self.close.rolling(120).mean() / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 MAC120：120 日移动均线。
- 来源证据：Factor/libraries/technical_indicators.py / mac120 / 第 63-65 行；总览匹配行 2380、2388
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### mac20
- 主分类：待复核
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 rolling=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 MAC20：20 日移动均线。
- 源码计算片段："""聚宽 MAC20：20 日移动均线。""" return self.close.rolling(20).mean() / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 MAC20：20 日移动均线。
- 来源证据：Factor/libraries/technical_indicators.py / mac20 / 第 55-57 行；总览匹配行 2354、2362
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### mac5
- 主分类：待复核
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 rolling=5；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 MAC5：5 日移动均线。
- 源码计算片段："""聚宽 MAC5：5 日移动均线。""" return self.close.rolling(5).mean() / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 MAC5：5 日移动均线。
- 来源证据：Factor/libraries/technical_indicators.py / mac5 / 第 47-49 行；总览匹配行 2328、2336
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### mac60
- 主分类：待复核
- 因子库来源：technical_indicators（经典技术指标兼容集合）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 rolling=60；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：聚宽 MAC60：60 日移动均线。
- 源码计算片段："""聚宽 MAC60：60 日移动均线。""" return self.close.rolling(60).mean() / self.close
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：聚宽 MAC60：60 日移动均线。
- 来源证据：Factor/libraries/technical_indicators.py / mac60 / 第 59-61 行；总览匹配行 2367、2375
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### average_directional_index
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：abs、ewm、均值
- 计算结构：字段 未从局部源码提取；算子 abs、ewm、mean；窗口 window=14；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：平均趋向指标：趋势强度，不区分涨跌方向。
- 源码计算片段："""平均趋向指标：趋势强度，不区分涨跌方向。""" positive, negative = self._directional_indices(window) dx = 100 * (positive - negative).abs() / (positive + negative + 1e-10) return dx.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的abs、ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 源码局部未识别字段 和 abs、ewm、均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：平均趋向指标：趋势强度，不区分涨跌方向。
- 来源证据：Factor/libraries/technical_lib.py / average_directional_index / 第 336-340 行；总览匹配行 1245、1252
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### bollinger_breakout
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、均值、滚动窗口、标准差
- 计算结构：字段 close；算子 mean、rolling、std；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：布林带突破：收盘价超出上轨为 1，低于下轨为 -1，否则 0。
- 源码计算片段："""布林带突破：收盘价超出上轨为 1，低于下轨为 -1，否则 0。""" mid = self.close.rolling(window).mean() std = self.close.rolling(window).std() upper = mid + n_std * std lower = mid - n_std * std breakout = (self.close > upper).astype(float) - (self.close < lower).astype(float) return breakout
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口、标准差，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：布林带突破：收盘价超出上轨为 1，低于下轨为 -1，否则 0。
- 来源证据：Factor/libraries/technical_lib.py / bollinger_breakout / 第 117-124 行；总览匹配行 871、879
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### bollinger_position
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、均值、滚动窗口、标准差
- 计算结构：字段 close；算子 mean、rolling、std；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：布林带位置：（收盘价 - 下轨）/（上轨 - 下轨）。
- 源码计算片段："""布林带位置：（收盘价 - 下轨）/（上轨 - 下轨）。""" mid = self.close.rolling(window).mean() std = self.close.rolling(window).std() upper = mid + n_std * std lower = mid - n_std * std return (self.close - lower) / (upper - lower + 1e-10)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口、标准差，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：布林带位置：（收盘价 - 下轨）/（上轨 - 下轨）。
- 来源证据：Factor/libraries/technical_lib.py / bollinger_position / 第 103-109 行；总览匹配行 839、847
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### bollinger_width
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、均值、滚动窗口、标准差
- 计算结构：字段 close；算子 mean、rolling、std；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：布林带宽度：（上轨 - 下轨）/ 中轨。
- 源码计算片段："""布林带宽度：（上轨 - 下轨）/ 中轨。""" mid = self.close.rolling(window).mean() std = self.close.rolling(window).std() return (2 * n_std * std) / mid
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口、标准差实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口、标准差，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：布林带宽度：（上轨 - 下轨）/ 中轨。
- 来源证据：Factor/libraries/technical_lib.py / bollinger_width / 第 111-115 行；总览匹配行 856、864
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### coppock_curve
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、apply、收益变化、滚动窗口、求和
- 计算结构：字段 close；算子 apply、pct_change、rolling、sum；窗口 short=11、long=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：科波克曲线：两段收益率之和的线性加权平滑。
- 源码计算片段："""科波克曲线：两段收益率之和的线性加权平滑。""" rate_of_change = self.close.pct_change(short) * 100 + self.close.pct_change(long) * 100 weights = np.arange(1, smooth + 1, dtype=float) return rate_of_change.rolling(smooth).apply( lambda values: np.dot(values, weights) / weights.sum(), raw=True )
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的apply、收益变化、滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 apply、收益变化、滚动窗口、求和，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：科波克曲线：两段收益率之和的线性加权平滑。
- 来源证据：Factor/libraries/technical_lib.py / coppock_curve / 第 266-272 行；总览匹配行 1152、1159
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### directional_range_balance
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、clip、滚动窗口、历史位移、求和、where
- 计算结构：字段 close；算子 clip、rolling、shift、sum、where；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：方向性区间平衡：上涨与下跌方向真实区间的净平衡强度。
- 源码计算片段："""方向性区间平衡：上涨与下跌方向真实区间的净平衡强度。""" window = self._validate_window(window) previous_close = self.close.shift() true_range = self._true_range() change = self.close - previous_close direction = change.gt(0).astype(float) - change.lt(0).astype(float) signed_range = (direction * true_range).where( change.notna() & true_range.notna() ) numerator = signed_range.rolling(window).sum() denominator = true_range.rolling(window).sum() result = numerator / (denominator + 1e-10) result = result.where(denominator.notna()) return re…
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的clip、滚动窗口、历史位移、求和、where实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 clip、滚动窗口、历史位移、求和、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：方向性区间平衡：上涨与下跌方向真实区间的净平衡强度。
- 来源证据：Factor/libraries/technical_lib.py / directional_range_balance / 第 416-432 行；总览匹配行 1408、1417
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### dpo
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、均值、滚动窗口、历史位移
- 计算结构：字段 close；算子 mean、rolling、shift；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：去趋势价格振荡器：移位收盘价减去当期均线。
- 源码计算片段："""去趋势价格振荡器：移位收盘价减去当期均线。""" displacement = window // 2 + 1 return self.close.shift(displacement) - self.close.rolling(window).mean()
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口、历史位移实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口、历史位移，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：去趋势价格振荡器：移位收盘价减去当期均线。
- 来源证据：Factor/libraries/technical_lib.py / dpo / 第 177-180 行；总览匹配行 622、993、1000
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### elder_force_index
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、volume、diff、ewm、均值
- 计算结构：字段 close、volume；算子 diff、ewm、mean；窗口 window=13；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：艾达尔强力指数：成交量加权收盘价变动的指数平滑值。
- 源码计算片段："""艾达尔强力指数：成交量加权收盘价变动的指数平滑值。""" raw_force = self.close.diff() * self.volume return raw_force.ewm(span=window, adjust=False).mean()
- 本类中的具体角色：它在“待复核”总论中具体通过 close、volume 的diff、ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close、volume 和 diff、ewm、均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close、volume；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：艾达尔强力指数：成交量加权收盘价变动的指数平滑值。
- 来源证据：Factor/libraries/technical_lib.py / elder_force_index / 第 261-264 行；总览匹配行 1140、1147
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### gain_loss_asymmetry
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、clip、log、收益变化、滚动窗口、求和
- 计算结构：字段 close；算子 clip、log、pct_change、rolling、sum、where；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：收益非对称性：窗口内上涨收益与下跌收益总量的对数比。
- 源码计算片段："""收益非对称性：窗口内上涨收益与下跌收益总量的对数比。""" window = self._validate_window(window) returns = self.close.pct_change(fill_method=None).replace( [np.inf, -np.inf], np.nan ) gains = returns.clip(lower=0.0).rolling(window).sum() losses = (-returns.clip(upper=0.0)).rolling(window).sum() result = np.log((gains + 1e-10) / (losses + 1e-10)) return result.where(gains.notna() & losses.notna())
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的clip、log、收益变化、滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 clip、log、收益变化、滚动窗口、求和、where，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：收益非对称性：窗口内上涨收益与下跌收益总量的对数比。
- 来源证据：Factor/libraries/technical_lib.py / gain_loss_asymmetry / 第 480-489 行；总览匹配行 1494、1503
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### kaufman_efficiency_ratio
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、abs、clip、diff、滚动窗口、求和
- 计算结构：字段 close；算子 abs、clip、diff、rolling、sum；窗口 window=10；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：Kaufman 路径效率：净价格变化与实际路径长度之比。
- 源码计算片段："""Kaufman 路径效率：净价格变化与实际路径长度之比。""" window = self._validate_window(window) net_change = self.close.diff(window).abs() path_length = self.close.diff().abs().rolling(window).sum() return (net_change / (path_length + 1e-10)).clip(lower=0.0, upper=1.0)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、clip、diff、滚动窗口、求和实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、clip、diff、滚动窗口、求和，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：Kaufman 路径效率：净价格变化与实际路径长度之比。
- 来源证据：Factor/libraries/technical_lib.py / kaufman_efficiency_ratio / 第 366-371 行；总览匹配行 1303、1312
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### ma_cross
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 fast=5、slow=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：均线交叉：短期均线 / 长期均线 - 1。
- 源码计算片段："""均线交叉：短期均线 / 长期均线 - 1。""" ma_fast = self.close.rolling(fast).mean() ma_slow = self.close.rolling(slow).mean() return ma_fast / ma_slow - 1
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：均线交叉：短期均线 / 长期均线 - 1。
- 来源证据：Factor/libraries/technical_lib.py / ma_cross / 第 35-39 行；总览匹配行 705、713
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### ma_distance
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、均值、滚动窗口
- 计算结构：字段 close；算子 mean、rolling；窗口 fast=5、slow=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：均线距离：(短期 - 长期) / 长期。
- 源码计算片段："""均线距离：(短期 - 长期) / 长期。""" ma_fast = self.close.rolling(fast).mean() ma_slow = self.close.rolling(slow).mean() return (ma_fast - ma_slow) / ma_slow
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：均线距离：(短期 - 长期) / 长期。
- 来源证据：Factor/libraries/technical_lib.py / ma_distance / 第 41-45 行；总览匹配行 720、728
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### negative_directional_index
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 window=14；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：负向方向指标：Wilder 平滑后的下行方向运动强度。
- 源码计算片段："""负向方向指标：Wilder 平滑后的下行方向运动强度。""" _, negative = self._directional_indices(window) return negative
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 源码局部未识别字段 和 若干算术操作，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：负向方向指标：Wilder 平滑后的下行方向运动强度。
- 来源证据：Factor/libraries/technical_lib.py / negative_directional_index / 第 331-334 行；总览匹配行 1233、1240
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### normalized_linear_regression_slope
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、abs、均值、滚动窗口
- 计算结构：字段 close；算子 abs、mean、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：归一化滚动线性回归斜率：斜率除以滚动均价绝对值。
- 源码计算片段："""归一化滚动线性回归斜率：斜率除以滚动均价绝对值。""" slope, _ = self._rolling_regression(window) mean_price = self.close.rolling(window).mean() return slope / (mean_price.abs() + 1e-10)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：归一化滚动线性回归斜率：斜率除以滚动均价绝对值。
- 来源证据：Factor/libraries/technical_lib.py / normalized_linear_regression_slope / 第 373-377 行；总览匹配行 1320、1329
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### positive_directional_index
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 window=14；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：正向方向指标：Wilder 平滑后的上行方向运动强度。
- 源码计算片段："""正向方向指标：Wilder 平滑后的上行方向运动强度。""" positive, _ = self._directional_indices(window) return positive
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 源码局部未识别字段 和 若干算术操作，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：正向方向指标：Wilder 平滑后的上行方向运动强度。
- 来源证据：Factor/libraries/technical_lib.py / positive_directional_index / 第 326-329 行；总览匹配行 1221、1228
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### regression_r_squared
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：无
- 计算结构：字段 未从局部源码提取；算子 未提取；窗口 window=20；滞后 same_day_or_unknown
- 公式/实现摘要：索引说明：滚动线性回归拟合优度 R²，衡量趋势路径的稳定程度。
- 源码计算片段："""滚动线性回归拟合优度 R²，衡量趋势路径的稳定程度。""" _, r_squared = self._rolling_regression(window) return r_squared
- 本类中的具体角色：它在“待复核”总论中具体通过 源码局部未识别字段 的算术和条件组合实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 源码局部未识别字段 和 若干算术操作，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 源码局部未识别字段；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：滚动线性回归拟合优度 R²，衡量趋势路径的稳定程度。
- 来源证据：Factor/libraries/technical_lib.py / regression_r_squared / 第 379-382 行；总览匹配行 1336、1345
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### true_strength_index
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、abs、diff、ewm、均值
- 计算结构：字段 close；算子 abs、diff、ewm、mean；窗口 short=13、long=25；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：真实强度指数：双重平滑价格动量相对绝对动量的比值。
- 源码计算片段："""真实强度指数：双重平滑价格动量相对绝对动量的比值。""" momentum = self.close.diff() smooth_momentum = momentum.ewm(span=long, adjust=False).mean().ewm( span=short, adjust=False ).mean() smooth_absolute = momentum.abs().ewm(span=long, adjust=False).mean().ewm( span=short, adjust=False ).mean() return 100 * smooth_momentum / (smooth_absolute + 1e-10)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、diff、ewm、均值实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、diff、ewm、均值，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：未检测到额外结构风险；仍需按数据可得时点和缺失值规则复核。
- 索引说明：真实强度指数：双重平滑价格动量相对绝对动量的比值。
- 来源证据：Factor/libraries/technical_lib.py / true_strength_index / 第 274-283 行；总览匹配行 1167、1174
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### ulcer_index
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、abs、滚动最大值、均值、滚动窗口
- 计算结构：字段 close；算子 abs、max、mean、rolling；窗口 window=14；滞后 historical_lag_or_rolling
- 公式/实现摘要：索引说明：Ulcer Index：滚动回撤百分比平方均值的平方根。
- 源码计算片段："""Ulcer Index：滚动回撤百分比平方均值的平方根。""" window = self._validate_window(window) rolling_max = self.close.rolling(window).max() drawdown_pct = 100 * (self.close - rolling_max) / (rolling_max.abs() + 1e-10) return drawdown_pct.pow(2).rolling(window).mean().pow(0.5)
- 本类中的具体角色：它在“待复核”总论中具体通过 close 的abs、滚动最大值、均值、滚动窗口实现该类信号，方向仍由最终符号和排名决定。
- 经济直觉：源码使用 close 和 abs、滚动最大值、均值、滚动窗口，当前证据不足以稳定归入文章五类，保留为待复核特征。
- 数据依赖与适用场景：依赖 close；适合用于研究特征结构和数据依赖的语义复核。
- 方向与限制：滚动窗口前置样本不足时会产生空值
- 索引说明：Ulcer Index：滚动回撤百分比平方均值的平方根。
- 来源证据：Factor/libraries/technical_lib.py / ulcer_index / 第 384-389 行；总览匹配行 1351、1360
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

### sma 公式族（3 个参数变体）

这组因子的共同公式是 `ma = self.close.rolling(window).mean() return (self.close - ma) / ma`。共同输入字段为 close，主要算子为 mean、rolling；参数梯度为 window ∈ {5, 20, 60}。

族级解读：共同公式比较当前 close 与 window 日均值的偏离；窗口越长，均值基准越平滑、信号响应越慢。 当前分类为“待复核”，所以先在这里解释共同经济结构，下面的成员标记只保留每个因子的精确名称、参数和来源证据。

成员：sma_5、sma_20、sma_60。

**因子：sma_5**
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、均值、滚动窗口
- 本条参数差异：沿用上述“sma 公式族”；本因子参数为 window=5。
- 计算结构：字段 close；算子 mean、rolling；窗口 window=5；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=5；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；滚动窗口前置样本不足时会产生空值。
- 索引说明：5 日均线乖离率：（收盘价 - 均线）/ 均线。
- 来源证据：Factor/libraries/technical_lib.py / sma_5 / 第 20-23 行；总览匹配行 663、671
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：sma_20**
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、均值、滚动窗口
- 本条参数差异：沿用上述“sma 公式族”；本因子参数为 window=20。
- 计算结构：字段 close；算子 mean、rolling；窗口 window=20；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=20；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；滚动窗口前置样本不足时会产生空值。
- 索引说明：20 日均线乖离率。
- 来源证据：Factor/libraries/technical_lib.py / sma_20 / 第 25-28 行；总览匹配行 677、685
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

**因子：sma_60**
- 主分类：待复核
- 因子库来源：technical_lib（技术指标、趋势拟合、价格形态和日内状态）
- 辅助标签：close、均值、滚动窗口
- 本条参数差异：沿用上述“sma 公式族”；本因子参数为 window=60。
- 计算结构：字段 close；算子 mean、rolling；窗口 window=60；滞后 historical_lag_or_rolling
- 本类中的具体角色：本条沿用上述共同源码主体，只取 window=60；该参数改变观察尺度或计算范围，公式族的经济逻辑不变。
- 数据依赖与限制：依赖 close；滚动窗口前置样本不足时会产生空值。
- 索引说明：60 日均线乖离率。
- 来源证据：Factor/libraries/technical_lib.py / sma_60 / 第 30-33 行；总览匹配行 691、699
- 与因子库总览一致性：mentioned
- 语义置信度：中：基于当前源码结构和索引说明

## 5. 三方一致性与待复核清单

当前目录级校验通过，但以下事项仍需要研究人员在数据和交易时点层面复核：

- 文章的 IndNeut 标记与 SVQuant 当前源码调用数量并不完全相同，应逐条确认行业字段、分组回退和中性化结果。
- VWAP、ADV、cap/total_mv 在不同数据源下可能是原始字段、成交额/成交量推导或近似值；报告中的经济直觉不等同于原论文的逐值复现。
- 使用当日 OHLC/VWAP 的因子需要明确是在收盘后生成次日信号，还是依赖盘中执行；A 股 T+1、涨跌停和停牌规则会改变可执行性。
- 动态模板因子共享一段生成源码；报告保留了每个具体因子的名称、字段和窗口，但模板级解释仍需结合实际数据字段确认。
- futureRes 已标记为未来数据/不可交易标签；任何其他出现 lead、negative shift、future 或 target 的新因子也必须进入同一复核流程。

## 6. 方法局限

本报告解释计算结构和可能的经济直觉，不证明预测能力。文章的原始背景是美股大盘股，迁移到 A 股需要独立验证；单因子也不等于策略。分类逻辑可以帮助组合和复核，但不能替代样本外回测、交易成本、数据可得性和风险约束分析。

文章来源：https://coriva.eu.org/alpha101-overview/
