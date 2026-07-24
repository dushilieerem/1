# FEAT-010 字段字典（v1.0）

> 状态：待数据源样本确认。本文是本 Feature 的字段命名、口径与可见性单一事实来源；数据源字段只能映射到本文的标准字段，不能由因子代码自行解释。

## 1. 通用约定

- 标准字段名使用小写 `snake_case`；一个标准名只对应一个业务口径。供应商原字段名、映射规则和单位换算记录在数据清单的字段映射附件中。
- 面板字段均为交易日 × 证券代码宽表，文件名为 `<field>.parquet`，索引列为 `datetime`；数值缺失使用 `NaN`，布尔或枚举缺失使用空值，禁止以 `0`、前值或未来值替代。
- 金额统一为**人民币元**，股数统一为**股**，比例统一为**小数**（例如 5% 记为 `0.05`）；价格单位为元/股。导入前完成单位换算并保存原始单位。
- 财务字段均为公告日点时字段：仅在 `announcement_date <= trade_date` 后可见。`_ttm` 表示当时可见的最近四个单季之和；缺少任一季度则为 `NaN`。
- `close` 是既有行情兼容字段，口径必须由当前数据清单声明；新增计算不得假定其复权方式。需要确定口径时，显式使用 `close_unadjusted`、`close_forward_adjusted` 或 `close_backward_adjusted`。

## 2. 已有行情与证券状态字段

| 标准字段 | 中文名 | 单位 / 类型 | 频率 | 口径与可见性 | MVP 状态 |
|---|---|---|---|---|---|
| `open` / `high` / `low` / `close` | 开/高/低/收盘价 | 元/股 | 日 | 既有兼容行情字段；复权口径由数据清单逐版本声明 | 复用，待盘点 |
| `volume` | 成交量 | 股 | 日 | 当日成交量 | 复用，待盘点 |
| `amount` | 成交额 | 元 | 日 | 当日成交金额 | 复用，待盘点 |
| `turnover` | 换手率 | 小数 | 日 | 数据源定义的换手率；必须说明分母为总股本或流通股本 | 复用，待盘点 |
| `total_shares` / `float_shares` | 总/流通股本 | 股 | 日 | 当日可得的总/流通股份数 | 复用，待盘点 |
| `total_mv` / `float_mv` | 总/流通市值 | 元 | 日 | 收盘价 × 对应股本；必须与价格复权口径一致 | 复用，待盘点 |
| `pe_ttm` / `pb` / `ps_ttm` | 市盈率 / 市净率 / 市销率 | 倍 | 日 | 供应商日频估值；保留其计算口径和源版本 | 复用，待盘点 |
| `is_st` | ST 标识 | bool | 日 | 当日证券是否处于 ST 或 *ST 状态 | 复用，待盘点 |
| `limit_up` | 涨停标识 | bool | 日 | 当日收盘是否触及涨停；不等同于不可买入 | 复用，待盘点 |
| `close_unadjusted` | 未复权收盘价 | 元/股 | 日 | 企业行为调整前的原始收盘价 | 新增 |
| `adj_factor` | 复权因子 | 正数 | 日 | 数据源定义的累计复权因子；必须在清单声明基日与公式 | 新增 |
| `close_forward_adjusted` | 前复权收盘价 | 元/股 | 日 | 由未复权价与 `adj_factor` 按已声明公式计算 | 新增 |
| `close_backward_adjusted` | 后复权收盘价 | 元/股 | 日 | 由未复权价与 `adj_factor` 按已声明公式计算 | 新增 |
| `listing_status` | 上市状态 | enum | 日 | `listed`、`suspended_listing`、`delisted`；退市后不得默认仍可交易 | 新增 |
| `is_suspended` | 停牌标识 | bool | 日 | 该交易日是否停牌；缺失不等同于未停牌 | 新增 |
| `is_tradable` | 可交易标识 | bool | 日 | 由上市、停牌、涨跌停及可选流动性规则产生；规则版本必须入清单 | 新增 |

## 3. 财务标准字段

| 标准字段 | 中文名 | 单位 | 分类 | 点时口径 | MVP 状态 |
|---|---|---:|---|---|---|
| `total_assets` | 资产总计 | 元 | 资产负债表 | 期末余额，公告后向前填充至下次有效披露 | 新增 |
| `current_assets` | 流动资产合计 | 元 | 资产负债表 | 同上 | 新增 |
| `total_liabilities` | 负债合计 | 元 | 资产负债表 | 同上 | 新增 |
| `current_liabilities` | 流动负债合计 | 元 | 资产负债表 | 同上 | 新增 |
| `total_equity` | 所有者权益合计 | 元 | 资产负债表 | 同上 | 新增 |
| `equity_attributable_to_parent` | 归母股东权益 | 元 | 资产负债表 | 同上 | 新增 |
| `cash_and_cash_equivalents` | 货币资金 | 元 | 资产负债表 | 同上 | 新增 |
| `inventory` | 存货 | 元 | 资产负债表 | 同上 | 新增 |
| `accounts_receivable` | 应收账款 | 元 | 资产负债表 | 同上 | 新增 |
| `accounts_payable` | 应付账款 | 元 | 资产负债表 | 同上 | 新增 |
| `operating_revenue_ttm` | 营业收入 TTM | 元 | 利润表 | 当时可见最近四个单季之和 | 新增 |
| `operating_cost_ttm` | 营业成本 TTM | 元 | 利润表 | 同上 | 新增 |
| `gross_profit_ttm` | 毛利 TTM | 元 | 利润表 | `operating_revenue_ttm - operating_cost_ttm`；保留推导关系 | 新增 |
| `operating_profit_ttm` | 营业利润 TTM | 元 | 利润表 | 当时可见最近四个单季之和 | 新增 |
| `total_profit_ttm` | 利润总额 TTM | 元 | 利润表 | 同上 | 新增 |
| `net_profit_ttm` | 净利润 TTM | 元 | 利润表 | 当时可见最近四个单季之和 | 新增 |
| `net_profit_attributable_ttm` | 归母净利润 TTM | 元 | 利润表 | 当时可见最近四个单季之和 | 新增 |
| `net_cashflow_operating_ttm` | 经营活动现金流净额 TTM | 元 | 现金流量表 | 当时可见最近四个单季之和 | 新增 |
| `basic_eps_ttm` | 基本每股收益 TTM | 元/股 | 每股指标 | 当时可见最近四个单季之和；不得用年末股本静态估算替代 | 新增 |

## 4. 基准与后续保留字段

| 标准字段 | 中文名 | 单位 / 类型 | 频率 | 状态 / 说明 |
|---|---|---|---|---|
| `market_return_all_a` | 全 A 流通市值加权收益 | 小数 | 日 | MVP 新增；以 t-1 流通市值加权 t 日可交易证券收益，计算规则版本化 |
| `industry_sw_l1` | 申万一级行业 | 分类代码 | 日 | 后续；必须保留生效区间，不能使用最新静态分类回填历史 |
| `consensus_eps_fy1` | 一致预期 EPS（未来一年） | 元/股 | 日 | 后续；记录预测期间、统计日期与机构覆盖数 |
| `dividend_cash_per_share` | 每股现金分红 | 元/股 | 事件 | 后续；记录公告、除权除息与到账日期 |
| `short_term_borrowings` / `long_term_borrowings` | 短期 / 长期借款 | 元 | 季 | 后续；作为资本结构明细，不以合计字段替代 |
| `risk_free_rate_annual` | 年化无风险利率 | 小数 | 日 | 后续；必须注明期限和年化/日化换算规则 |

## 5. 原始财务记录的必填元数据

每条原始记录至少包含 `symbol`、`report_period`、`announcement_date`、`statement_type`、`field`、`value`、`unit`、`source`、`source_version`、`revision_at`。其中 `statement_type` 为 `balance_sheet`、`income_statement` 或 `cashflow_statement`；流量表还须有 `period_type`（`quarter` 或 `year_to_date`），以支持可审计的单季与 TTM 转换。关键元数据缺失的记录不得进入标准面板。

## 6. 变更控制

- 新增字段、废弃字段或改变口径，必须先更新本文、数据清单和版本号，再生成数据。
- 不兼容变更使用新字段名；不得改变已有标准字段的含义。废弃字段保留至少一个已验证数据版本，并在清单标注替代字段。
- 字段字典的可机读副本将在数据导入实现时以 `field_dictionary.yaml` 随数据版本发布；本文件是其评审基线。
