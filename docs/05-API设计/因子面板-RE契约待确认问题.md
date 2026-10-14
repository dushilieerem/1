# 因子面板 · 待 RE 确认 2 项

> 提出方：SVQuant 集成侧　对象：ResearchEngine
> 2026-10-14　**结论均已核对 RE 源码**（`/home/dev01/project/ResearchEngine`），非推测

分组方向那件事已查清：**RE 实现自洽，是 SVQuant 自己的两份文档把 `Q1`/`Q5` 写反了**，已在 SVQuant 侧修正（依据与结论见 `因子面板-RE接口契约.md` §7，含 RE 源码引用）。**RE 无需为此改动。**

以下两项仍需 RE 回复。

---

## 一、逐分位换手：能否提供？

**现状（RE 源码）**

- `app/schemas/backtest.py:283-299` 的 `QuantileMetric` 字段为
  `quantile / annual_return / volatility / sharpe / max_drawdown / annual_excess_return / excess_volatility / information_ratio / benchmark_win_rate` —— **没有换手**。
- 换手只在主组合上算一次：`app/services/metric/metrics/standard.py:188-200`
  ```
  # 单边换手 = sum(|Δw|) / 2
  turnover = pos.diff().abs().iloc[1:].sum(axis=1) / 2.0
  return float(turnover.mean())
  ```
  即 `metrics.turnover` = **整个组合的平均单边换手**，不是分位换手。

**可行性**：RE 已经为每个分组构造目标权重（`app/services/portfolio/engine.py:75-109` `_group_target`），
换手公式也是现成的 —— 逐分位换手不需要新机制，只是目前没算、没暴露。

**请求**

1. 能否在 `quantile_metrics[]` 上增加 `turnover`（口径沿用现有定义：平均单边换手 `mean(Σ|Δw|/2)`）？
   若不便扩展该结构，在 `layered_returns` 里加 `turnover1..turnoverN` 亦可。
2. 请顺带明确口径：单边还是双边、是否年化、在调仓日还是逐日平均。

**SVQuant 为什么需要**：面板的换手列现在只能显示整组合换手。契约 §6 明确「不可把组合总换手伪称为
Q1/Q5 换手」，所以该列已按实情改名为「组合换手」—— 若 RE 能提供逐分位换手，我们再补「最高分位 Q1 /
最低分位 Q5 换手」两列。

---

## 二、IC 全空却无 error：属失败还是「不可用」？

**现状（RE 源码）**：`app/services/metric/engine.py:396-434` 的 `_factor_statistics` 在四种情况下
返回 `_empty_factor_statistics()`（`ic_series` 空、`ic_mean`/`rank_ic_mean`/`ic_std` 全 `null`、
`valid_days = 0`），**且不报错**：

| # | 条件 | 位置 |
|---|---|---|
| 1 | `factor_values` 或 `forward_returns` 为 `None` | `:405` |
| 2 | 无共同日期或无共同标的 | `:409` |
| 3 | 逐日有效样本 < 2：`valid = factor.notna() & future.notna()` 后无一行达标 | `:414-421` |
| 4 | 逐日相关系数全为 `NaN`（分母 ≤ 0，即横截面零方差） | `:393`、`:431-434` |

**实测**：`SV02_0002` / `SV06_0004` / `SV09_0008`（共 331 个因子中的 3 个）命中此路径 ——
`error = null`、`ic_series = []`、IC 各字段 `null`，但 `quantile_metrics` 与 `cumulative_series` 正常。
以 `SV02_0002` 为例，各分位年化仍有区分度：

```
Q1 7.20%   Q2 8.65%   Q3 9.49%   Q4 6.59%   Q5 0.70%   基准 5.77%
```

即因子值与分组可用，只是 IC 序列为空。SVQuant 无法从响应判断命中的是条件 3 还是 4。

**请求**

1. 上述 3 个因子命中的是哪一种条件？（若是「因子在横截面上零方差」这类数据特性，属正常；若是
   条件 1/2 这类配置或取数问题，可能需要排查。）
2. 契约 §8 要求「单因子数据缺失、因子异常或计算失败 → `status: failed` + `error_code`」。
   RE 是否认为「IC 不可用」应归入该类？
   - 若应归入：请按 §8 标记；
   - 若属另一类（RE 当前行为）：请在契约里单列该状态，例如在 `factor_analysis` 上给出
     `ic_unavailable_reason`，或在 `ic_series` 为空时于 `definition` 中注明原因。
   SVQuant 好据此在面板上区分「无 IC（因子无区分度）」与「计算失败」。

**SVQuant 侧的临时处理**：RE 响应里 `ic_series` 为空是可判定的信号，`map_yg_response` 里能据此检出这
3 行（**尚未接线**）。在 RE 明确前，面板不把它们标为失败 —— 不编造、也不误报，IC 列按 `null` 显示
「—」。RE 回复后按确认口径补齐标注。
