# POST /api/backtest/factor

用于因子选股研究。服务以原始因子值 `pd.qcut` 分组构建组合，返回绩效、净值、基准、超额收益和因子分析。

```jsonc
{
  "factor_code": "def momentum(self, window=5):\n    return self.close.pct_change(window)",
  "factor_name": "momentum",
  "portfolio_type": "long_only",
  "universe": "CSI300",
  "start": "2024-01-01", "end": "2024-12-31",
  "rebalance_days": 1, "groups": 5,
  "benchmark": "CSI300", "analysis_level": "core"
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `factor_code` | string | — | 自定义因子函数。未传时必须传单个 `library_name`。 |
| `library_name` | string/string[] | — | 内置库；自定义因子可传多个以复用方法。 |
| `factor_name` | string | `alpha101` | 要执行的函数名。 |
| `portfolio_type` | enum | `long_only` | `long_only` 或 `long_short`。 |
| `universe` | string | `CSI300` | 股票池。 |
| `universe_snapshot` | object/null | `null` | WebApp 已鉴权并解析的静态证券池快照；与 `universe` 至多传一个。 |
| `start` / `end` | string/null | `null` | 回测区间，格式 `YYYY-MM-DD`。 |
| `rebalance_days` | integer | `1` | 正整数交易日。 |
| `groups` | integer | `5` | 2–10 组。 |
| `benchmark` | enum | `CSI300` | `CSI300`、`CSI500`、`CSI1000` 或 `SSE50`。 |
| `benchmark_snapshot` | object/null | `null` | WebApp 已鉴权并解析的固定权重组合基准快照；与 `benchmark` 至多传一个。 |
| `analysis_level` | enum | `core` | `core` 或 `full`；后者增加 IC/IR、FF3、行业曲线。 |
| `commission_rate` | number | `0.0` | 手续费率。 |
| `stamp_tax` | number | `0.0` | 卖出印花税率。 |
| `slippage_rate` | number | `0.0` | 滑点率。 |

### 日期语义

`start/end` 是收益确认区间，不是因子计算区间。服务端会先用当前数据版本的完整可用历史计算因子（包括区间起点之前的预热数据），再将因子值、收盘价、远期收益、分层结果、指标和净值裁剪到请求区间。因子不需要额外声明 `warmup_days`；因子实现仍需自行避免使用未来数据。

还支持 `filter_limit_up`、`filter_suspended`、`commission_rate`、`stamp_tax`、`slippage_rate`；完整示例和因子写法见 [因子与策略指南](../07-factor-strategy-guide.md)。

成功响应包含 `metrics`、`equity_curve`、`drawdowns`、`annual_returns`、`factor_analysis`、`date_range`、`final_equity`、`benchmark_curve`、`excess_return`、`meta` 和 `error`。因子代码错误保持 HTTP `200`，并写入 `error`（此时 `meta` 为 `null`）。

`factor_analysis.quantile_metrics` 返回各因子分位（`Q1` 为最高分位，`QN` 为最低分位）及基准的绩效。分组的 `annual_return`、`volatility`、`sharpe` 和 `max_drawdown` 是分组自身的绝对绩效；`annual_excess_return`、`excess_volatility`、`information_ratio` 和 `benchmark_win_rate` 是相对基准指标。最后一项 `quantile: "benchmark"` 返回基准的绝对绩效，相对基准字段为 `null`：

```json
[
  {
    "quantile": "Q1",
    "annual_return": 0.12,
    "volatility": 0.18,
    "sharpe": 0.67,
    "max_drawdown": -0.21,
    "annual_excess_return": 0.03,
    "excess_volatility": 0.10,
    "information_ratio": 0.30,
    "benchmark_win_rate": 0.52
  },
  {
    "quantile": "benchmark",
    "annual_return": 0.09,
    "volatility": 0.15,
    "sharpe": 0.60,
    "max_drawdown": -0.18,
    "annual_excess_return": null,
    "excess_volatility": null,
    "information_ratio": null,
    "benchmark_win_rate": null
  }
]
```

其中，分组 `annual_return` 使用包含首个信号到入场日收益的完整收益序列计算几何年化 CAGR，分组 `volatility`/`sharpe` 使用样本标准差 `ddof=1`；基准使用入场日到结束日的收益序列，首个入场日收益保留为 `0`，年化同样使用几何 CAGR，波动率/夏普使用样本标准差 `ddof=1`。分组净值曲线首个输出点统一为 `1.0`，首个信号收益只进入分组绝对指标，不进入展示曲线或相对基准指标。

相对基准指标只使用分组与基准都有数据的共同交易日：`annual_excess_return` 为共同区间分组几何年化收益减去基准几何年化收益，`excess_volatility` 为日超额收益样本标准差（`ddof=1`）年化，`information_ratio` 为年化超额收益除以超额年化波动；`benchmark_win_rate` 为共同日期上分组当日收益大于基准累计收益的占比，等于时不计为胜。基准累计收益从共同区间首日归一化净值计算。`core` 与 `full` 均返回该字段；若分组或基准没有足够有效数据，对应指标为 `null`。

因子回测响应的 `meta` 会明确返回因子价格和收益价格的复权口径、字段、逻辑来源及精度策略。当前默认策略为：因子使用后复权 OHLC，收益使用后复权 close，均来自研究行情 `data_engine`，读取源精度且不额外四舍五入。`display/unadjusted_price.parquet` 只用于行情展示接口，不参与因子计算。

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
