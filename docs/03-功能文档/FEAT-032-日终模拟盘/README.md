# FEAT-032：日终模拟盘

- 状态：待批准 / 设计中
- 所属 Initiative：[INIT-002：交易执行](../../01-需求文档/项目倡议/INIT-002-交易执行/README.md)
- 所属能力：实盘/模拟盘 / 交易执行
- 优先级：P1
- 上游：[INIT-002 交易执行领域设计](../../01-需求文档/项目倡议/INIT-002-交易执行/domain-design.md)、[FEAT-010 投研数据底座](../FEAT-010-投研数据底座/README.md)
- 关联架构：[系统架构](../../02-架构文档/system_architecture.md)、[回测引擎设计](../../02-架构文档/engine-design.md)

> 本 Feature 定义的是日终批量模拟盘，不是实时行情驱动的模拟交易，也不是券商实盘接入。
> ResearchEngine 负责确定性信号与执行计算；SVQuant 负责账户生命周期、持久化账本、日终调度和用户侧接口。

## 1. 价值与范围

### 1.1 用户场景

用户绑定一段策略代码、股票池和模拟账户。交易日 `D` 收盘后，数据服务发布当日完整日频数据，系统使用截至 `D-1` 的信息生成 `D` 日订单，并以 `D` 日成交额除以成交量得到的 VWAP 作为模拟成交价。用户可以在 SVQuant 查看资金、持仓、成交、费用和每日净值。

该流程是“收盘后结算已提交的 D 日订单”，不是收盘后才使用 D 日收盘信息下单。这样可以保持信号时序没有未来函数。

### 1.2 必须做

- 支持事件策略和向量化策略两种已有执行模式。
- 事件策略只读取截至 `D-1` 的可见数据，并恢复跨日 `context.state`。
- 向量化策略只读取截至 `D-1` 的数据，取得最后一个有效目标权重后转换为 D 日订单。
- 使用日频 `amount`、`volume` 计算 `VWAP = amount / volume`，不依赖分钟数据。
- 使用现金多头账户、整手、卖后买、T+1、涨跌停、现金和交易成本规则。
- 订单按 VWAP 全量成交；返回订单、成交、费用、下一持仓状态和收盘权益。
- ResearchEngine 提供单日同步内部结算接口，不写账户数据库。
- SVQuant 持久化账户、持仓、订单、成交、净值和策略运行状态，并保证日终结算幂等。

### 1.3 可以以后做

- 实时/盘中行情驱动。
- 部分成交、成交量参与率、滑点和市场冲击。
- 多空、融券、保证金、强平和多资产账户。
- 券商接入、实盘订单路由和真实成交回报。
- 自动识别并处理分红、送转、配股等公司行为。

### 1.4 明确不做

- ResearchEngine 不建立用户账户表、订单数据库或用户权限体系。
- ResearchEngine 不负责日终任务调度、重试、通知和前端页面。
- 本 Feature 不读取分钟数据，不新增实时行情连接。
- 本 Feature 不自动检测公司行为；跨公司行为日期的模拟结果不作准确性保证。

## 2. 业务规则与场景

### 2.1 日终时序

```text
数据发布方将 D 日完整数据发布到 ResearchEngine 的 `marketdata/`
        ↓
SVQuant 日终任务确认 release 和交易日
        ↓
ResearchEngine 读取 D-1 可见数据生成信号
        ↓
ResearchEngine 读取 D 日 amount / volume / 未复权 close
        ↓
按 D 日 VWAP 计算并执行订单
        ↓
ResearchEngine 返回 fills、费用、下一持仓和收盘权益
        ↓
SVQuant 事务性保存账户账本和结算快照
```

`D` 必须是交易日；`D-1` 是不晚于 `D` 的上一个交易日。D 日数据未完整发布时不得使用前一版本数据静默结算。

### 2.2 数据和价格口径

| 用途 | 数据口径 | 规则 |
|---|---|---|
| 策略信号 | 现有研究行情及策略所需字段 | 最大可见日期为 `D-1` |
| 模拟成交 | 日频 `amount / volume` | `volume <= 0`、缺失或非有限值时不成交，不回退到 close 或典型价格 |
| 收盘估值 | 未复权日收盘价 | 用于计算 D 日持仓市值和总权益 |
| 股票状态 | D 日交易状态 | 用于涨跌停及可交易性校验 |

当前日频研究行情已经包含 `amount`、`volume`，但当前数据字典明确未提供独立 `vwap` 字段；VWAP 在 ResearchEngine 的交易价格视图中派生，不新增物理 VWAP 文件。未复权 close 需要通过统一数据读取契约暴露给 ResearchEngine。[当前数据字典](../FEAT-010-投研数据底座/09-current-data-fields.md)

### 2.3 事件策略

- 使用已有 `initialize(context)` 契约。
- `context.data` 只能看到 `D-1` 及之前的数据。
- SVQuant 传入上次结算返回的 `strategy_state`；ResearchEngine 将更新后的 JSON 状态原样返回。
- 若非空 `strategy_state` 对应的代码哈希与本次代码不一致，返回 `STRATEGY_STATE_VERSION_MISMATCH`，不得静默继续运行。
- 策略产生的 `target_quantity`、`target_value` 和 `close` 意图统一转换为订单，再交由日频执行器处理。

### 2.4 向量化策略

- 使用截至 `D-1` 的完整前缀行情调用 `generate_signals()`。
- `NaN` 沿用既有语义：保持上一有效目标；取 `D-1` 的最后有效目标权重。
- 目标权重必须为非负数且总权重不超过 1；负权重返回 `UNSUPPORTED_PORTFOLIO`。
- 以 D 日 VWAP 和账户 D 日执行前总权益把目标权重转换成整手目标数量。
- 之后与事件策略使用同一现金、T+1、涨跌停和费用执行器。

### 2.5 账户和成交规则

SVQuant 传入的账户输入在业务上仍是“现金 + 持仓”，但每项持仓必须包含执行所需字段：

```json
{
  "symbol": "000001.SZ",
  "quantity": 1000,
  "available_quantity": 1000,
  "average_cost": 12.30
}
```

ResearchEngine 不持有账户，但会返回更新后的 `cash` 和同样结构的 `positions`。执行规则如下：

- 卖出订单先于买入订单；
- 买入数量按 `lot_size=100` 整手；
- 卖出数量不得超过 `available_quantity`；
- 买入检查现金及最低手续费；
- 买入涨停、卖出跌停时拒单；
- 成交价统一为该标的 D 日 VWAP；
- 卖出计提印花税，买卖均计提佣金；
- 不模拟部分成交，符合条件的订单一次全量成交；
- 没有有效 VWAP 的标的返回 `NO_VWAP`，不使用替代价格。

### 2.6 公司行为边界

本 Feature 不新增公司行为数据和自动检测逻辑。SVQuant 可以在产品层提示该限制，但 ResearchEngine 不声明跨除权除息、分红或送转日期的账户净值准确性。后续若纳入公司行为，必须新增数据契约和独立 Feature/ADR。

## 3. 模块职责与方案设计

### 3.1 职责分工

| 模块 | 负责内容 | 明确不负责 |
|---|---|---|
| ResearchEngine | 数据可见性、策略执行、VWAP 派生、订单归一化、交易规则、费用、成交和下一状态计算 | 账户持久化、用户认证、调度、重试、前端 |
| SVQuant | 账户和策略配置、`strategy_state`、账本、订单/成交/快照、日终任务、幂等、用户 API/UI | 不复制 ResearchEngine 的成交和交易规则 |
| ResearchEngine / `marketdata` | 提供 D 日 `amount`、`volume`、未复权 close、研究字段及 release 清单 | 不维护模拟账户和订单状态 |

### 3.2 ResearchEngine 内部接口

新增内部接口：

```text
POST /api/internal/paper-trading/settle
```

该接口一次只计算一个结算日，采用同步响应。请求核心字段：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `settlement_date` | 是 | D 日 |
| `engine_mode` | 是 | `event` 或 `vectorized` |
| `strategy_code` | 是 | 本次运行的完整策略源码；仅限受信任 SVQuant 内部调用 |
| `expected_code_hash` | 否 | 调用方可提供的 SHA-256 校验值 |
| `universe` | 是 | 命名股票池或既有资产引用 |
| `account.cash` | 是 | D 日执行前现金 |
| `account.positions` | 是 | 含数量、可卖数量、平均成本的持仓数组 |
| `strategy_state` | 否 | 事件策略跨日 JSON 状态 |
| `strategy_state_code_hash` | 否 | 状态绑定的策略代码哈希 |
| `execution` | 否 | 佣金、最低佣金、印花税、整手等规则覆盖 |

响应核心字段：

```json
{
  "status": "settled",
  "settlement_date": "2026-09-08",
  "signal_date": "2026-09-07",
  "data_release_id": "ifind-sync-...",
  "code_hash": "sha256:...",
  "orders": [],
  "fills": [],
  "next_account": {
    "cash": 1000000.0,
    "positions": [],
    "total_equity": 1000000.0
  },
  "strategy_state": {},
  "fees": {"commission": 0.0, "stamp_tax": 0.0},
  "warnings": [],
  "assumptions": {}
}
```

HTTP 语义：

- `200`：结算计算完成；单笔拒单通过订单状态表达；
- `409`：`DATA_NOT_READY`、策略状态哈希不匹配或数据 release 不一致；
- `422`：请求字段、策略源码、模式或组合方向不合法；
- `500`：ResearchEngine 内部未预期错误。

ResearchEngine 不保存响应。SVQuant 必须在事务中保存结算响应，并以以下组合生成幂等键：

```text
(paper_account_id, settlement_date, strategy_config_revision, data_release_id)
```

同一幂等键重复调用不得重复记账；数据 release 发生变化时必须由 SVQuant 显式发起重算或回滚。

### 3.3 ResearchEngine 实施拆分

1. 增加交易价格视图，读取日频 `amount`、`volume` 和未复权 close，并派生 VWAP。
2. 抽取现金账户执行器，统一事件策略和向量化策略的订单执行规则。
3. 增加结算请求/响应、账户输入、持仓、订单、成交和结算结果模型。
4. 增加事件策略的 `strategy_state` 恢复/序列化和代码哈希校验。
5. 增加向量化目标权重到整手订单的适配器。
6. 新增内部同步路由；不改变现有 `/api/backtest/strategy` 回测接口。

### 3.4 SVQuant 实施拆分

1. 建立模拟账户、持仓、策略状态、订单、成交和日快照存储。
2. 保存策略代码、代码哈希、配置修订号和 `strategy_state`。
3. 在数据 release 发布完成后触发 D 日结算；失败可重试，成功后原子提交。
4. 提供账户创建、启停、资金、持仓、订单、成交、净值和结算状态接口。
5. 通过 Feature Flag 控制首期灰度，保留按 release 重放和回滚能力。

## 4. 兼容性、风险与回滚

- 现有策略回测接口、事件回测的历史输出和向量化回测接口保持不变。
- 新接口仅供 SVQuant 内部使用，不把策略源码结算接口暴露给公网用户。
- 策略源码执行沿用当前 ResearchEngine 的受信任代码边界；若未来开放不受信任用户代码，必须单独增加沙箱、资源限制和权限设计。
- 使用未复权 close 做账户估值；策略信号与账户估值价格口径不同，响应中必须记录 `signal_price_source` 和 `mark_price_source`。
- 公司行为暂不自动识别；产品和接口文档必须展示该限制。
- 回滚方式：SVQuant 关闭模拟盘 Feature Flag，停止日终任务；现有回测路由和数据 release 不回滚、不覆盖。

## 5. 验收与测试

### 5.1 ResearchEngine 测试

- `amount / volume` VWAP 计算、缺失值、零成交量和非有限值测试；确认不读取分钟数据。
- D-1 信号可见性测试：事件和向量化策略均不能读取 D 日信号字段。
- 事件策略 `context.state` 两次结算往返测试，包括入场日期、峰值等状态。
- 向量化 `NaN` 前向保持、目标权重和整手数量转换测试。
- 卖后买、现金不足、T+1、涨停/跌停、手续费、印花税和平均成本测试。
- VWAP 成交与未复权 close 估值口径测试。
- 相同输入、策略代码和 data release 的确定性测试。
- 代码哈希变化、状态哈希不匹配、数据未就绪和不支持多空的错误测试。

### 5.2 SVQuant 联调验收

- 同一账户同一交易日重复触发不会重复写入订单、成交和费用。
- ResearchEngine 成功响应可以一次事务提交为账户下一状态。
- 失败重试不丢失上一账户状态；release 变化不会静默覆盖旧结算。
- 账户页面展示现金、可用数量、平均成本、成交 VWAP、费用和收盘权益。
- Feature Flag 关闭后日终任务停止，既有策略回测不受影响。

### 5.3 完成标准

1. ResearchEngine 内部结算接口契约冻结并通过自动化测试。
2. SVQuant 可对一个事件策略和一个向量化策略完成连续多个交易日结算。
3. 结算结果可重放、可审计，且同一输入不会产生不同成交结果。
4. 文档中的未实现能力没有被 API 或 UI 误标为已支持。

## 6. 实施里程碑

| 里程碑 | 负责方 | 交付物 |
|---|---|---|
| M0 | 双方 | Feature 批准、接口和价格口径冻结 |
| M1 | ResearchEngine | 交易价格视图、VWAP 派生和通用现金执行器 |
| M2 | ResearchEngine | 事件/向量化适配、策略状态、内部结算 API |
| M3 | SVQuant | 账户账本、日终调度、幂等提交和用户接口 |
| M4 | 双方 | 连续多日联调、黄金样例、灰度和回滚演练 |

## 7. 决策记录

- 日终结算，不做实时模拟。
- D-1 生成信号，D 日 VWAP 成交。
- VWAP 使用日频 `amount / volume`，不使用分钟数据。
- 首期现金多头、全量 VWAP 成交，不做部分成交和市场冲击。
- ResearchEngine 无状态、不持久化；SVQuant 持久化账本、调度和账户接口。
- 持仓记录包含 `quantity`、`available_quantity`、`average_cost`；策略运行状态单独作为 opaque JSON 保存。
- 每次允许传入策略源码，但必须计算和记录代码哈希。
- 首期不自动处理公司行为，跨公司行为日期的结果不保证准确。
