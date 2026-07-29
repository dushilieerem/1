# POST /api/backtest/factor

用于因子选股研究。服务以 `FactorQuantileStrategy` 按因子值分组构建组合，返回绩效、净值、基准、超额收益和因子分析。

```jsonc
{
  "factor_code": "def momentum(self, window=5):\n    return self.close.pct_change(window)",
  "factor_name": "momentum",
  "portfolio_type": "long_short",
  "universe": "CSI_ALL",
  "start": "2024-01-01", "end": "2024-12-31",
  "rebalance_days": 15, "groups": 5,
  "benchmark": "CSI500", "analysis_level": "core"
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `factor_code` | string | — | 自定义因子函数。未传时必须传单个 `library_name`。 |
| `library_name` | string/string[] | — | 内置库；自定义因子可传多个以复用方法。 |
| `factor_name` | string | `alpha101` | 要执行的函数名。 |
| `portfolio_type` | enum | `long_short` | `long_only` 或 `long_short`。 |
| `universe` | string | `CSI_ALL` | 股票池。 |
| `start` / `end` | string/null | `null` | 回测区间，格式 `YYYY-MM-DD`。 |
| `rebalance_days` | integer | `20` | 正整数交易日。 |
| `groups` | integer | `5` | 2–10 组。 |
| `benchmark` | enum | `CSI300` | `CSI300`、`CSI500`、`CSI1000` 或 `SSE50`。 |
| `analysis_level` | enum | `core` | `core` 或 `full`；后者增加 IC/IR、FF3、行业曲线。 |

还支持 `filter_limit_up`、`filter_suspended`、`commission_rate`、`stamp_tax`、`slippage_rate`；完整示例和因子写法见 [因子与策略指南](../07-factor-strategy-guide.md)。

成功响应包含 `metrics`、`equity_curve`、`drawdowns`、`annual_returns`、`factor_analysis`、`date_range`、`final_equity`、`benchmark_curve`、`excess_return`、`meta` 和 `error`。因子代码错误保持 HTTP `200`，并写入 `error`（此时 `meta` 为 `null`）。

服务端固定使用配置的数据目录和 Native 回测后端；`backtest_period`、`data_dir`、`backtest_engine`、`initial_capital`、`include_equity`、`include_factor_values`、`include_positions`、`rebalance`、`stock_num` 等旧字段会返回 `422`。
