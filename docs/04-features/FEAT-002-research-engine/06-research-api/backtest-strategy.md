# POST /api/backtest/strategy

用于自定义策略逻辑。可提交带 `generate_signals()` 的自由策略，使用 `FactorPortfolioStrategy` 定义多个 `@factor` 和唯一 `@signal` 的结构化因子组合策略，或引用 `Strategy/libraries/index.yaml` 中已保存的向量化策略版本。

```jsonc
{
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

成功响应包含 `metrics`、`equity_curve`、`drawdowns`、`annual_returns`、`date_range`、`final_equity`、`benchmark_curve`、`excess_return`、`meta`、可选 `positions`、可选 `rebalance_logs` 和 `error`。使用已保存策略时，`meta` 额外返回 `strategy_id`、实际 `strategy_version` 与源码 `code_hash`。策略代码、数据或运行错误保持 HTTP `200` 并写入 `error`。

`strategy_params`、`factor_code`、`factor_name`、`data_dir`、`backtest_engine`、`include_equity` 和未知字段会返回 `422`。策略代码示例见 [因子与策略指南](../07-factor-strategy-guide.md)。
