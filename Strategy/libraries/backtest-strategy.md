# POST /api/backtest/strategy

用于向量化或事件驱动策略。通过 `engine_mode` 显式选择：`vectorized`（默认）支持 `generate_signals()` 与 `FactorPortfolioStrategy`；`event` 支持实现 `initialize(context)` 的日频事件策略。引用策略目录时，请求模式必须与资产的 `execution_mode` 一致。

```jsonc
{
  "engine_mode": "vectorized",
  "strategy_code": "class MyStrategy: ...",
  "universe": "CSI500",
  "start": null, "end": null,
  "benchmark": "CSI300",
  "commission_rate": 0.0, "stamp_tax": 0.001,
  "slippage_rate": 0.0, "initial_capital": 1000000,
  "include_positions": false, "include_rebalance_logs": true
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `strategy_code` | string/null | — | 完整 Python 源码；与 `strategy_id` 二选一。 |
| `engine_mode` | enum | `vectorized` | `vectorized` 或 `event`；决定策略契约和回测引擎。 |
| `strategy_id` | string/null | — | 已保存策略 ID；与 `strategy_code` 二选一。 |
| `strategy_version` | string/null | `null` | 已保存策略版本；省略时使用 `index.yaml` 中的 `current_version`。 |
| `universe` | string | `CSI500` | 股票池。 |
| `start` / `end` | string/null | `null` | 回测区间，格式 `YYYY-MM-DD`。 |
| `benchmark` | enum | `CSI300` | `CSI300`、`CSI500`、`CSI1000` 或 `SSE50`。 |
| `commission_rate` / `slippage_rate` | number | `0.0` | 按成交额的费率与滑点率。 |
| `stamp_tax` | number | `0.001` | 卖出印花税率。 |
| `initial_capital` | number | `1000000` | 初始资金。 |
| `include_positions` | boolean | `false` | 返回持仓权重快照。 |
| `include_rebalance_logs` | boolean | `false` | 返回目标权重变化日志。 |

## 成功响应示例

以下示例省略了 `equity_curve`、`benchmark_curve` 和 `positions` 的其余数据点；实际响应会返回完整序列。数值仅用于说明结构，不代表真实回测表现。

```json
{
  "metrics": {
    "annual_return": 0.1842,
    "sharpe": 1.3568,
    "sortino": 1.9021,
    "calmar": 1.7455,
    "max_drawdown": -0.1055,
    "volatility": 0.1634,
    "ic": null,
    "rank_ic": null,
    "win_rate": 0.5317,
    "turnover": 0.0842,
    "total_return": 0.2015
  },
  "equity_curve": [
    {"date": "2024-01-02", "value": 1000000.0, "drawdown": 0.0},
    {"date": "2024-01-03", "value": 1012500.0, "drawdown": 0.0},
    {"date": "2024-01-04", "value": 1008000.0, "drawdown": -0.004444}
  ],
  "drawdowns": [
    {
      "start": "2024-01-03",
      "end": "2024-01-04",
      "peak": 1012500.0,
      "trough": 1008000.0,
      "recovery": "2024-01-08",
      "depth": -0.004444,
      "days": 5
    }
  ],
  "annual_returns": [{"year": 2024, "return_value": 0.2015}],
  "date_range": {"start": "2024-01-02", "end": "2024-12-31"},
  "final_equity": 1201500.0,
  "benchmark_curve": [
    {"date": "2024-01-02", "value": 1.0, "drawdown": 0.0},
    {"date": "2024-01-03", "value": 1.006, "drawdown": 0.0}
  ],
  "excess_return": 0.0832,
  "meta": {
    "strategy": "EqualWeightMomentum",
    "universe": "CSI500",
    "benchmark": "CSI300",
    "strategy_id": null,
    "strategy_version": null,
    "code_hash": null
  },
  "positions": [
    {
      "date": "2024-01-02",
      "holdings": [
        {"symbol": "000001.SZ", "name": "平安银行", "weight": 0.1},
        {"symbol": "600000.SH", "name": "浦发银行", "weight": 0.1}
      ]
    }
  ],
  "rebalance_logs": [
    {
      "date": "2024-01-02",
      "trades": [
        {
          "symbol": "000001.SZ",
          "name": "平安银行",
          "side": "buy",
          "previous_weight": 0.0,
          "target_weight": 0.1,
          "weight_change": 0.1
        }
      ]
    }
  ],
  "error": null
}
```

## 响应字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `metrics` | object | 标准绩效指标。指标无法计算时，对应值为 `null`；自由策略没有因子值和远期收益，因此 `ic`、`rank_ic` 通常为 `null`。 |
| `equity_curve` | object[]/`null` | 策略每日账户权益和回撤序列；`value` 为金额，起点通常等于 `initial_capital`。 |
| `drawdowns` | object[] | 最大的至多 10 段回撤，按回撤深度（最负优先）排序。无回撤时为空数组。 |
| `annual_returns` | object[] | 按自然年计算的区间收益。某年不足两个有效交易日时不返回该年。 |
| `date_range` | object | 实际用于计算的净值序列起止日期；没有有效净值时两个字段均为 `null`。 |
| `final_equity` | number/`null` | 回测结束日的策略账户权益金额。 |
| `benchmark_curve` | object[]/`null` | 基准收盘价按首日归一化后的净值和回撤序列，首个 `value` 为 `1.0`。 |
| `excess_return` | number/`null` | 策略区间收益减去同期基准区间收益，不是逐日超额收益序列。 |
| `meta` | object/`null` | 本次回测实际采用的策略、股票池与基准信息。执行失败时为 `null`。 |
| `positions` | object[]/`null` | 仅当请求 `include_positions=true` 且存在持仓时返回；为控制体积，最多采样 60 个日期，每日只保留权重最高的 20 个标的。 |
| `rebalance_logs` | object[]/`null` | 仅当请求 `include_rebalance_logs=true` 且有调仓记录时返回，按调仓日聚合。 |
| `orders` / `fills` / `event_positions` / `events` / `assumptions` | object[]/object/`null` | 仅事件模式返回：订单、成交、账户快照、调度审计轨迹和执行假设。 |
| `error` | string/`null` | 业务执行错误信息；成功时为 `null`。 |

### `metrics` 指标

| 字段 | 含义 |
|------|------|
| `annual_return` | 日均策略收益乘以 252 得到的年化收益率。 |
| `total_return` | 整个回测区间的累计收益率，等于末日权益除以首日权益减 1。 |
| `sharpe` / `sortino` | 无风险利率为 0 的年化夏普比率 / 索提诺比率。 |
| `calmar` | 年化收益率除以最大回撤绝对值。 |
| `max_drawdown` | 区间最大回撤，使用负数表示回撤。 |
| `volatility` | 按 252 个交易日年化的收益率波动率。 |
| `win_rate` | 日收益为正的交易日占比。 |
| `turnover` | 相邻日期持仓权重变化计算的平均单边换手率。 |
| `ic` / `rank_ic` | 因子值与远期收益的截面 Pearson / Spearman 相关均值；仅有可用因子数据时才可能有值。 |

### 嵌套对象

| 对象 | 字段 | 说明 |
|------|------|------|
| 净值点（`equity_curve`、`benchmark_curve`） | `date`、`value`、`drawdown` | 日期为 `YYYY-MM-DD`；`drawdown` 是相对历史最高值的回撤，取值小于等于 0。 |
| 回撤段（`drawdowns`） | `start`、`end`、`peak`、`trough`、`recovery`、`depth`、`days` | `start` 是高点日，`end` 是最低点日，`recovery` 为恢复到此前高点的日期；未恢复则为 `null`。`days` 为从高点到恢复日（未恢复时到回测末日）的自然日数。 |
| 年度收益（`annual_returns`） | `year`、`return_value` | 自然年份及该年首末有效净值点计算的收益率。 |
| 元信息（`meta`） | `strategy`、`universe`、`benchmark` | 实际执行的策略类名、股票池和基准。 |
| 已保存策略元信息（`meta`） | `strategy_id`、`strategy_version`、`code_hash` | 仅通过 `strategy_id` 运行时有值：策略 ID、实际使用版本和源码 SHA-256 哈希；直接提交源码时均为 `null`。 |
| 持仓快照（`positions`） | `date`、`holdings` | `holdings` 是 `{symbol, name, weight}` 数组。`symbol` 为带交易所后缀的代码（如 `000001.SZ`），`name` 为证券名称，`weight` 为目标持仓权重。 |
| 调仓日志（`rebalance_logs`） | `date`、`trades` | `trades` 为 `{symbol, name, side, previous_weight, target_weight, weight_change}` 数组；`symbol` 与 `name` 的口径同持仓快照，`side` 取 `buy` 或 `sell`。 |

## 业务错误响应示例

策略源码、策略目录、数据或回测执行出错时，接口仍返回 HTTP `200`，由调用方检查 `error` 判断是否成功；此时其他结果字段使用默认空值，`meta` 为 `null`。

```json
{
  "metrics": {},
  "equity_curve": null,
  "drawdowns": [],
  "annual_returns": [],
  "date_range": {"start": null, "end": null},
  "final_equity": null,
  "benchmark_curve": null,
  "excess_return": null,
  "meta": null,
  "positions": null,
  "rebalance_logs": null,
  "error": "ValueError: 策略代码必须且只能定义一个包含 generate_signals 方法的类"
}
```

请求体不符合参数约束（例如 `strategy_code` 与 `strategy_id` 同时提供、必填二选一缺失，或包含未知字段）时，FastAPI 返回 HTTP `422`，不使用上述业务错误结构。

`strategy_params`、`factor_code`、`factor_name`、`data_dir`、`backtest_engine`、`include_equity` 和未知字段会返回 `422`。策略代码示例见 [因子与策略指南](../07-factor-strategy-guide.md)。
