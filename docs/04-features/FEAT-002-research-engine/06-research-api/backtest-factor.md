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
| `universe_snapshot` | object/null | `null` | WebApp 已鉴权并解析的静态证券池快照；与 `universe` 至多传一个。 |
| `start` / `end` | string/null | `null` | 回测区间，格式 `YYYY-MM-DD`。 |
| `rebalance_days` | integer | `20` | 正整数交易日。 |
| `groups` | integer | `5` | 2–10 组。 |
| `benchmark` | enum | `CSI300` | `CSI300`、`CSI500`、`CSI1000` 或 `SSE50`。 |
| `benchmark_snapshot` | object/null | `null` | WebApp 已鉴权并解析的固定权重组合基准快照；与 `benchmark` 至多传一个。 |
| `analysis_level` | enum | `core` | `core` 或 `full`；后者增加 IC/IR、FF3、行业曲线。 |

还支持 `filter_limit_up`、`filter_suspended`、`commission_rate`、`stamp_tax`、`slippage_rate`；完整示例和因子写法见 [因子与策略指南](../07-factor-strategy-guide.md)。

成功响应包含 `metrics`、`equity_curve`、`drawdowns`、`annual_returns`、`factor_analysis`、`date_range`、`final_equity`、`benchmark_curve`、`excess_return`、`meta` 和 `error`。因子代码错误保持 HTTP `200`，并写入 `error`（此时 `meta` 为 `null`）。

使用自定义资产的请求示例：

```json
{
  "factor_code": "def momentum(self):\n    return self.close.pct_change(20)",
  "factor_name": "momentum",
  "universe_snapshot": {"asset_id": "user-pool-42", "version": "3", "content_hash": "...", "symbols": ["000858", "600519"]},
  "benchmark_snapshot": {"asset_id": "user-benchmark-9", "version": "2", "content_hash": "...", "weights": {"000858": 0.5, "600519": 0.5}, "pricing": "close_to_close"}
}
```

成功时 `meta.universe_asset` 和 `meta.benchmark_asset` 分别返回 `{id, version, content_hash, constituent_count}`；证券池另有 `membership_mode: "static"`，组合基准另有 `pricing: "close_to_close"`。完整的实际成分和权重保存到运行结果元数据，不在 API 响应中展开。

静态证券池的每个代码必须存在于本次回测的 `close` 面板。组合基准要求所有成分在回测区间内有完整收盘价；权重必须为非负有限数且和为 1。违反这些规则时，接口返回 HTTP `200` 且 `error` 包含可读业务错误；混用旧参数与 `*_snapshot` 时返回 HTTP `422`。ResearchEngine 不保存、列举或按 ID 查询用户资产。

服务端固定使用配置的数据目录和 Native 回测后端；`backtest_period`、`data_dir`、`backtest_engine`、`initial_capital`、`include_equity`、`include_factor_values`、`include_positions`、`rebalance`、`stock_num` 等旧字段会返回 `422`。
