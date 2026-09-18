# `marketdata` 外部数据字典

> 本文记录 ResearchEngine 使用的外部 `marketdata/` release 数据字典。该目录已经移出 SVQuant，字段、文件和覆盖规模以实际 Parquet schema、`data_manifest.yaml` 与 `quality_report.json` 为准。
>
> - 数据版本：`ifind-sync-20260908-055514`
> - 清单生成时间：`2026-09-08T05:55:14.511492+00:00`（UTC）
> - 质量状态：`active_validated`
> - 当前来源：iFinD
> - 缺失值策略：原样保留，不在发布阶段填零、前向填充或用未来值补齐

## 1. 结论先看

当前已发布的 `marketdata/` release 包含 75 个已登记数据资产：

| 类型 | 资产数量 | 作用 |
|---|---:|---|
| 股票日频后复权行情 | 1 | 因子研究、日频回测 |
| 股票日频未复权行情 | 1 | SVQuant K 线展示 |
| 日频估值与证券状态 | 1 | 估值、行业、涨跌停和上市状态研究 |
| 1 分钟行情分区 | 66 | 已落盘的高频行情；当前暂无统一读取接口 |
| 指数日线 | 2 | CSI300、CSI500 基准指数 |
| 指数成分/权重 | 2 | CSI300、CSI500 股票池和权重快照 |
| 交易日历 | 1 | 全 A 交易日标记 |
| 证券主表 | 1 | 股票代码与名称映射 |

ResearchEngine 当前通过 `FieldParquetProvider` 暴露 15 个股票研究面板逻辑字段。行情文件中的字段名直接使用；`date_sequence` 的 iFinD 原始字段在边界统一去掉 `ths_` 前缀和 `_stock` 后缀：

```text
open high low close volume amount turnover
current_mv dividend_yield_ttm listed_status pb_mrq
pcf_operating_cash_flow_ttm pe_ttm the_sw_industry_code up_and_down_status
```

下列历史标准设计字段目前不属于本数据版本：`total_mv`、`float_mv`、`total_shares`、`float_shares`、`pe`、`pb`、`ps_ttm`、`industry_sw_code`、`limit_status`、`is_suspended`、`is_st`、`limit_up`、`limit_down`、`is_tradable`、`adj_factor`、`vwap`。

## 2. 物理文件与覆盖范围

| 文件/目录 | 粒度 | 当前规模 | 物理字段 | ResearchEngine 使用方式 |
|---|---|---|---|---|
| `market_data/market_data_hfq.parquet` | 交易日 × 证券 | 5,265 行、5,929 只证券 | `open`、`high`、`low`、`close`、`volume`、`amount`、`turnover` | 研究/回测主行情；通过 `get_panels()`、`get_bars()` 读取 |
| `date_sequence/date_sequence.parquet` | 交易日 × 证券 | 406 行、5,929 只证券 | `ths_current_mv_stock`、`ths_dividend_yield_ttm_stock`、`ths_listed_status_stock`、`ths_pb_mrq_stock`、`ths_pcf_operating_cash_flow_ttm_stock`、`ths_pe_ttm_stock`、`ths_the_sw_industry_code_stock`、`ths_up_and_down_status_stock` | 研究面板；边界逻辑字段为去掉 `ths_` 和 `_stock` 后的名称 |
| `unadjusted_price/unadjusted_price.parquet` | 交易日 × 证券 | 5,265 行、5,929 只证券 | `open`、`high`、`low`、`close` | 展示行情；`/api/market-data/daily/{symbol}` 使用 |
| `high_frequency/1min/2026/{6,7,8,9}/*.parquet` | 1 分钟 × 证券 × 交易日 | 66 个文件；每个文件 242 个时间点、5,929 只证券 | `open`、`high`、`low`、`close`、`volume`、`amount` | 已落盘，但当前 `DataEngine` 没有分钟级读取方法 |
| `index/index_price/index_price_000300.SH.parquet` | 交易日 × 指数 | 5,204 行、1 个指数 | `open`、`high`、`low`、`close` | `get_index("CSI300")` |
| `index/index_price/index_price_000905.SH.parquet` | 交易日 × 指数 | 4,227 行、1 个指数 | `open`、`high`、`low`、`close` | `get_index("CSI500")` |
| `index/index_weights/index_weights_000300.SH.parquet` | 权重快照日 × 证券 | 5,204 行、948 个证券列 | `<证券代码>`，单元格为 `weight` | CSI300 最新/点时成分解析 |
| `index/index_weights/index_weights_000905.SH.parquet` | 权重快照日 × 证券 | 4,237 行、1,706 个证券列 | `<证券代码>`，单元格为 `weight` | CSI500 最新/点时成分解析 |
| `calendar/calendar_all_a.parquet` | 日期 | 8,767 行 | `date`、`exchange`、`is_trade_day`、`source`、`marketcode` | 已落盘；当前没有统一 `DataEngine` 日历读取入口 |
| `universe/a_share.parquet` | 证券 | 5,929 行 | `thscode`、`name` | 全 A 股票池和证券名称映射 |

### 2.1 宽表结构

股票行情、估值和状态文件采用 Pandas/PyArrow 两级列：

```text
date
('000001.SZ', 'open')
('000001.SZ', 'close')
('000001.SZ', 'ths_pb_mrq_stock')
...
```

其中：

- 物理行索引字段为 `date`，Parquet 类型为 `timestamp[ns]`。
- 物理列为 `(证券代码, iFinD 原始字段)`；证券代码带交易所后缀，例如 `000001.SZ`。`market_data` 的行情字段保持原名；`date_sequence` 的 `ths_*_stock` 字段由边界映射为去掉前后缀后的逻辑字段，例如 `ths_current_mv_stock` → `current_mv`、`ths_pb_mrq_stock` → `pb_mrq`。
- 数值列的物理类型为 `double`，加载到 Pandas 后通常为 `float64`。
- 文本状态列加载为字符串；原始缺失值保留。
- Provider 输出 `{字段名: DataFrame}`，每个 DataFrame 的形状为“日期 × 证券”。输出面板列名归一为六位代码，例如 `000001`；`get_bars()` 同时兼容 `000001` 和 `000001.SZ`。

## 3. 股票研究面板字段字典

以下 15 个字段可以作为 `DataEngine` 逻辑字段请求，均在当前 Parquet 文件中有物理列；`date_sequence` 的 8 个字段通过边界规则从 iFinD 原始名映射而来。

| 字段 | 中文含义 | 类型 | 单位/值域 | 物理来源 | 口径与使用限制 |
|---|---|---|---|---|---|
| `open` | 开盘价 | `float64` | 元/股 | `market_data/market_data_hfq.parquet` | 研究行情为后复权开盘价；未复权展示行情另见第 4 节 |
| `high` | 最高价 | `float64` | 元/股 | 同上 | 与同文件其他 OHLC 使用同一后复权口径 |
| `low` | 最低价 | `float64` | 元/股 | 同上 | 与同文件其他 OHLC 使用同一后复权口径 |
| `close` | 收盘价 | `float64` | 元/股 | 同上 | 因子和日频回测默认使用后复权收盘价 |
| `volume` | 成交量 | `float64` | 股 | 同上 | 当日成交股数；缺失不等同于零成交 |
| `amount` | 成交额 | `float64` | 人民币元 | 同上 | iFinD `amt`；当前保留发布值，未在读取层换算 |
| `turnover` | 换手率 | `float64` | iFinD 原始值 | 同上 | iFinD `turn`；当前未做比例单位换算，不能默认解释为 `0~1` 小数 |
| `current_mv` | 当前市值 | `float64` | 供应商原始市值单位 | `ths_current_mv_stock` | iFinD 当前市值口径；不能在读取层当作 `total_mv` 或 `market_cap` 的同义字段 |
| `dividend_yield_ttm` | 滚动十二个月股息率 | `float64` | 供应商原始比例值 | `ths_dividend_yield_ttm_stock` | 当前未做百分比/小数尺度换算；使用前确认源字段单位 |
| `listed_status` | 上市状态 | `string` | 原始状态文本 | `ths_listed_status_stock` | 保留 iFinD 原始状态；不应直接当作 `is_tradable` 使用 |
| `pb_mrq` | 最近报告期市净率 | `float64` | 倍 | `ths_pb_mrq_stock` | 原始估值指标；负值、无效值和缺失由研究逻辑处理 |
| `pcf_operating_cash_flow_ttm` | 经营现金流滚动十二个月市现率 | `float64` | 倍 | `ths_pcf_operating_cash_flow_ttm_stock` | TTM 口径；不等同于市盈率 |
| `pe_ttm` | 滚动十二个月市盈率 | `float64` | 倍 | `ths_pe_ttm_stock` | 当前实际逻辑字段名是 `pe_ttm`；不再暴露旧的 `pe` |
| `the_sw_industry_code` | 申万行业代码 | `string` | 行业代码 | `ths_the_sw_industry_code_stock` | 只有行业代码，没有行业名称字段；覆盖期以该文件实际日期为准 |
| `up_and_down_status` | 涨跌停及停牌状态 | `string` | 原始状态文本 | `ths_up_and_down_status_stock` | 例如涨停、跌停、停牌或非涨跌停；过滤逻辑从该原始文本判断 |

### 3.1 字段覆盖的重要限制

`market_data_hfq` 和 `unadjusted_price` 均有 5,265 行，但 `date_sequence` 只有 406 行。因此估值、行业和上市状态字段不能假定覆盖全部行情日期，不能在读取层静默前向填充或使用最新状态回填历史。

`date_sequence` 的 8 个物理字段均使用 iFinD 原始命名，ResearchEngine 只暴露去掉 `ths_` 和 `_stock` 后的逻辑名。`current_mv` 存在，但 `total_mv`、`market_cap`、`total_shares` 和 `float_shares` 不存在。

## 4. 展示行情字段

`unadjusted_price/unadjusted_price.parquet` 提供与研究面板同名但口径不同的四个字段：

| 字段 | 中文含义 | 类型 | 单位 | 使用场景 |
|---|---|---|---|---|
| `open` | 未复权开盘价 | `float64` | 元/股 | SVQuant K 线展示 |
| `high` | 未复权最高价 | `float64` | 元/股 | SVQuant K 线展示 |
| `low` | 未复权最低价 | `float64` | 元/股 | SVQuant K 线展示 |
| `close` | 未复权收盘价 | `float64` | 元/股 | SVQuant K 线展示 |

该文件不提供 `volume`、`amount` 或 `turnover`。未复权价格不能与后复权研究价格混用，也不参与当前因子回测收益计算。

## 5. 1 分钟行情字段

路径 `high_frequency/1min/2026/<month>/<month.day>.parquet` 下的每个分区包含同一交易日的 242 个 1 分钟时间点，物理字段如下：

| 字段 | 中文含义 | 类型 | 单位 | 备注 |
|---|---|---|---|---|
| `open` | 分钟开盘价 | `float64` | 元/股 | 高频原始价格字段 |
| `high` | 分钟最高价 | `float64` | 元/股 | 高频原始价格字段 |
| `low` | 分钟最低价 | `float64` | 元/股 | 高频原始价格字段 |
| `close` | 分钟收盘价 | `float64` | 元/股 | 高频原始价格字段 |
| `volume` | 分钟成交量 | `float64` | 股 | 分钟成交股数 |
| `amount` | 分钟成交额 | `float64` | 人民币元 | 分钟成交金额 |

当前高频文件已通过 manifest 登记，但 `FieldParquetProvider` 只扫描日频业务域文件，不会将这些分区加入日频 `get_panels()` 字段列表；调用方不能把它们当作日频字段读取。

## 6. 指数、股票池和日历字段

### 6.1 指数日线

| 资产 | 支持标识 | 字段 | 类型 | 单位/含义 |
|---|---|---|---|---|
| `index/index_price/index_price_000300.SH.parquet` | `CSI300` / `000300.SH` | `open`、`high`、`low`、`close` | `float64` | 指数点位，不使用股票复权语义 |
| `index/index_price/index_price_000905.SH.parquet` | `CSI500` / `000905.SH` | `open`、`high`、`low`、`close` | `float64` | 指数点位，不使用股票复权语义 |

当前指数文件没有 `volume`、`amount` 或 `turnover`。`DataEngine.get_index()` 当前只支持 `CSI300` 和 `CSI500` 两个标识。

### 6.2 指数成分与权重

| 资产 | 字段形式 | 类型 | 含义 | 解析规则 |
|---|---|---|---|---|
| `index/index_weights/index_weights_000300.SH.parquet` | 每个证券代码一列 | `float64` | CSI300 在该快照日的权重 | 权重非空且大于 0 表示该证券属于 CSI300 |
| `index/index_weights/index_weights_000905.SH.parquet` | 每个证券代码一列 | `float64` | CSI500 在该快照日的权重 | 权重非空且大于 0 表示该证券属于 CSI500 |

权重值保留 iFinD 原始值，当前不在读取层做百分比换算。`get_universe("CSI300")` / `get_universe("CSI500")` 取最新快照；点时股票池使用不晚于指定日期的最近快照，禁止使用未来快照。

### 6.3 全 A 证券主表

`universe/a_share.parquet` 是静态证券集合，不是日频可交易股票池：

| 字段 | 类型 | 含义 | 注意事项 |
|---|---|---|---|
| `thscode` | `string` | 带交易所后缀的 iFinD 证券代码，例如 `000001.SZ` | 当前 5,929 行；用于与行情列匹配 |
| `name` | `string` | 证券名称 | 用于 SVQuant 代码名称映射；不表示某日一定在市或可交易 |

`CSI_ALL`、`ALL_A` 和 `A_SHARE` 使用该文件返回全 A 代码列表。缺少 `is_tradable`、上市日期和退市日期等点时字段。

### 6.4 全 A 交易日历

`calendar/calendar_all_a.parquet` 是普通长表，不是“日期 × 证券”面板：

| 字段 | 类型 | 当前值/含义 |
|---|---|---|
| `date` | `string` | `YYYY-MM-DD` 日期 |
| `exchange` | `string` | 当前为 `ALL_A` |
| `is_trade_day` | `bool` | 当前文件记录的日期为交易日，值为 `True` |
| `source` | `string` | 当前为 `ifind` |
| `marketcode` | `int64` | 当前为 `212100`，是 iFinD 请求市场代码，不是证券交易所后缀 |

该文件当前没有接入 `DataEngine` 的统一交易日历方法；回测中的 `PandasCalendar` 仍按面板日期或工作日规则工作。

## 7. 当前不可用字段清单

以下字段在历史标准字典、模型或因子文档中出现，但在当前 `marketdata` 活动版本中没有可读取的物理字段。调用这些名称时不应静默映射到相近字段：

| 字段 | 当前状态 | 不能替代的原因 |
|---|---|---|
| `total_mv` | 不提供 | 当前只有 `current_mv`，不能在读取层假定它等于总市值 |
| `float_mv` | 不提供 | 当前字段为 `current_mv`，不能据名称推断为流通市值 |
| `total_shares` | 不提供 | 没有总股本面板 |
| `float_shares` | 不提供 | 没有流通股本面板 |
| `pe` | 不提供 | 当前字段为 `pe_ttm`，不再暴露无口径的 `pe` |
| `pb` | 不提供 | 当前字段为 `pb_mrq`，报告期口径不能省略 |
| `pcf_ttm` | 不提供 | 当前字段为 `pcf_operating_cash_flow_ttm`，不能省略现金流口径 |
| `ps_ttm` | 不提供 | 没有 TTM 市销率面板 |
| `industry_sw_code` | 不提供 | 当前字段为 `the_sw_industry_code` |
| `industry_sw` | 不提供 | 当前只有申万行业代码，没有行业名称 |
| `is_st` | 不提供 | 没有 ST 日频状态字段 |
| `limit_status` | 不提供 | 当前字段为 `up_and_down_status` |
| `limit_up` / `limit_down` | 不提供 | `up_and_down_status` 是原始文本，不自动拆成两个布尔字段 |
| `is_suspended` | 不提供 | 当前暂不从其他字段派生停牌布尔值；停牌过滤按缺失字段跳过 |
| `market_cap` | 不提供 | `current_mv` 与策略所需市值口径不自动等同 |
| `is_tradable` | 不提供 | 当前没有综合上市、停牌、涨跌停和流动性规则的可交易标识 |
| `adj_factor` | 不提供 | 当前没有复权因子面板；后复权价格只作为已发布价格口径存在 |
| `vwap` | 不提供 | 可由研究逻辑按需要使用 `amount / volume` 近似，但不是数据字段 |
| `market_return_all_a` | 不提供 | 当前没有全 A 市值加权市场收益序列 |
| 指数 `volume` / `amount` / `turnover` | 不提供 | 当前指数价格文件只包含 OHLC |

因此 `ValueLib` 中依赖 `ps_ttm` 的 `sp_ttm` 和 `composite_value` 在当前 release
不能直接运行；保持缺字段失败，不把 `pcf_operating_cash_flow_ttm` 冒充为市销率。

## 8. 研究使用约定

1. 研究和回测价格使用 `market_data/market_data_hfq.parquet`；展示行情使用 `unadjusted_price/unadjusted_price.parquet`，不得混用。
2. 所有字段缺失均保留为缺失。研究员必须显式决定缺失处理、停牌处理、涨跌停处理和样本筛选规则。
3. `up_and_down_status`、`listed_status` 是原始文本字段。涨跌停过滤和事件成交限制从 `up_and_down_status` 判断；停牌过滤所需的 `is_suspended` 当前缺失时跳过，不从 `listed_status` 强行派生。
4. 不要根据字段名称猜测单位。尤其是 `turnover`、`dividend_yield_ttm` 和指数权重，当前发布保留供应商原始数值尺度。
5. `data_manifest.yaml` 记录资产字段清单和哈希，`quality_report.json` 记录发布质量检查结果；新增数据版本时必须同步更新本文的字段、规模和覆盖说明。

## 9. 事件策略字段兼容性

按当前 15 个逻辑字段审计 ResearchEngine 独立仓库已发布策略资产中声明为 `event` 的策略：共 72 个，66 个所需字段完整，6 个仍然缺字段。审计同时包含策略的 `required_market_state`；涨跌停状态统一使用 `up_and_down_status`，停牌字段不参与兼容映射。

| 事件策略 | 缺少字段 |
|---|---|
| `davis_double_play_a_share_event` | `inc_net_profit_year_on_year`、`roe` |
| `dividend_growth_a_share_event` | `dividend_cash_per_share`、`total_mv` |
| `fama_french_carhart_multi_factor_a_share_event` | `market_cap` |
| `neff_low_pe_a_share_event` | `inc_net_profit_year_on_year` |
| `net_operating_assets_anomaly_a_share_event` | `bond_payable`、`long_borr`、`market_cap`、`money_cap`、`total_assets`、`total_liabilities` |
| `piotroski_f_score_a_share_event` | `current_assets`、`current_liabilities`、`net_cashflow_operating_ttm`、`net_profit_ttm`、`operating_cost_ttm`、`operating_revenue_ttm`、`total_assets`、`total_liabilities`、`total_mv`、`total_shares` |

其中 `total_mv`、`market_cap` 不自动映射为 `current_mv`，会计字段也不以估值字段替代。上述 6 个策略在当前 release 上应明确报告缺字段并停止初始化，不做静默兼容。

## 10. 读取边界

本字典供 ResearchEngine 的数据 Provider 和契约测试使用。SVQuant 不直接实例化 Provider，不
读取 Parquet 文件，也不依赖文件名或目录层级。SVQuant 如需行情展示或研究数据，统一通过
ResearchEngine HTTP API 获取；接口响应中的字段语义必须与本字典和对应 API 契约一致。

数据 release 的版本、manifest 哈希和质量状态由 ResearchEngine 在自己的部署环境校验。发生
版本不匹配时，ResearchEngine 应拒绝计算，SVQuant 显示研究服务不可用，而不是使用本地旧数据。
