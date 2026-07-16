# 因子回测 API 文档

> 文档版本：v1.0
> 最后更新：2026-07-17
> 适用接口：`POST /api/backtest/factor`
> 系统级文档：[FEAT-002 Research API](../../docs/04-features/FEAT-002-research-engine/06-research-api.md)

## 1. 用途

前端提交因子函数体和回测参数。服务端按因子值做等权分层：`long_only` 持有最高组，
`long_short` 做多最高组并做空最低组；随后返回主组合、各层、基准和超额收益。

## 2. 请求示例

```json
{
  "factor_code": "def volume_20d(self, window: int = 20):\n    return self.volume / self.volume.rolling(window).mean()\n\ndef amount_20d(self, window: int = 20):\n    return self.amount / self.amount.rolling(window).mean()\n\ndef combo_factor(self):\n    return 0.5 * self.volume_20d() + 0.5 * self.amount_20d()",
  "factor_name": "combo_factor",
  "portfolio_type": "long_only",
  "universe": "CSI500",
  "start": "2024-01-01",
  "end": "2024-12-31",
  "rebalance_days": 15,
  "groups": 5,
  "benchmark": "CSI500",
  "commission_rate": 0.0003,
  "stamp_tax": 0.001,
  "slippage_rate": 0.001
}
```

## 3. 请求参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `factor_code` | string | 是 | — | 因子函数体；无需传入 import 或类定义。 |
| `factor_name` | string | 否 | `alpha101` | 要运行的因子方法名。 |
| `portfolio_type` | string | 否 | `long_short` | `long_only` 或 `long_short`。 |
| `universe` | string | 否 | `CSI_ALL` | 股票池，如 `CSI300`、`CSI500`、`CSI1000`。 |
| `start` / `end` | string/null | 否 | `null` | 回测起止日期，格式 `YYYY-MM-DD`；不传时使用全部可用数据。 |
| `filter_limit_up` | boolean | 否 | `true` | 涨停过滤开关；当前尚未接入执行链路。 |
| `filter_suspended` | boolean | 否 | `true` | 停牌过滤开关；当前尚未接入执行链路。 |
| `rebalance_days` | integer | 否 | `20` | 调仓间隔，单位为交易日；可传 `15`、`16` 等正整数。 |
| `groups` | integer | 否 | `5` | 分层数，范围 2–10。 |
| `benchmark` | string | 否 | `CSI300` | `CSI300`、`CSI500`、`CSI1000` 或 `SSE50`。 |
| `commission_rate` | number | 否 | `0.0003` | 佣金率。 |
| `stamp_tax` | number | 否 | `0.001` | 卖出印花税率。 |
| `slippage_rate` | number | 否 | `0.001` | 滑点率。 |

已移除字段：`backtest_period`、`data_dir`、`backtest_engine`、`initial_capital`、
`include_equity`、`include_factor_values`、`include_positions`、`rebalance`、`stock_num`。
传入这些字段将返回 HTTP `422`。

## 4. 返回示例

```json
{
  "metrics": { "annual_return": 0.18, "sharpe": 1.42, "ic": 0.02 },
  "equity_curve": [
    { "date": "2024-01-02", "value": 1.0, "drawdown": 0.0 }
  ],
  "factor_analysis": {
    "ic_mean": 0.02,
    "rank_ic_mean": 0.03,
    "layered_returns": { "groups": 5, "layer1": -0.03, "layer5": 0.18, "spread": 0.21 },
    "cumulative_series": [
      { "date": "2024-01-02", "layer1": 1.0, "layer2": 1.0, "layer3": 1.0, "layer4": 1.0, "layer5": 1.0 }
    ]
  },
  "benchmark_curve": [
    { "date": "2024-01-02", "value": 1.0, "drawdown": 0.0 }
  ],
  "excess_return": 0.06,
  "date_range": { "start": "2024-01-02", "end": "2024-12-31" },
  "final_equity": 1.18,
  "meta": {
    "factor": "combo_factor", "universe": "CSI500", "portfolio_type": "long_only",
    "rebalance_days": 15, "groups": 5, "benchmark": "CSI500",
    "filter_limit_up": true, "filter_suspended": true
  },
  "error": null
}
```

## 5. 返回字段

| 字段 | 说明 |
|------|------|
| `metrics` | 年化收益、夏普、最大回撤、IC、Rank IC 等绩效指标。 |
| `equity_curve` | 主组合净值点，包含日期、净值和回撤。 |
| `drawdowns` | 最多十段主要回撤。 |
| `annual_returns` | 各年度收益。 |
| `factor_analysis` | IC、Rank IC、各分层收益与各层累计净值。 |
| `benchmark_curve` | 所选基准的归一化净值。 |
| `excess_return` | 主组合相对基准的区间超额收益。 |
| `date_range` / `final_equity` | 实际回测区间与最终净值。 |
| `meta` | 本次回测实际采用的配置。 |
| `error` | 成功时为 `null`；因子代码或执行错误时填入错误信息。 |

因子代码错误不会返回 HTTP 500，而是返回 HTTP 200 且 `error` 非空；参数校验失败或传入已移除字段时返回 HTTP `422`。
