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

## 二、IC 全空却无 error：属失败还是「不可用」？ —— **RE 已回复（2026-10-14）**

**RE 结论：不属失败，已新增 `ic_unavailable_reason` 供区分。** 前文「现状」保留为提问时的记录；
RE 侧的答复、实测复核与落地字段见本节末尾。

### 提问时的现状（RE 源码）

`app/services/metric/engine.py` 的 `_factor_statistics` 在下列四种情况下返回
`_empty_factor_statistics()`（`ic_series` 空、`ic_mean`/`rank_ic_mean`/`ic_std` 全 `null`、
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

**SVQuant 侧的临时处理**（已被下述 RE 口径取代）：RE 响应里 `ic_series` 为空是可判定的信号，
`map_yg_response` 里能据此检出这 3 行（**尚未接线**）。在 RE 明确前，面板不把它们标为失败 ——
不编造、也不误报，IC 列按 `null` 显示「—」。

---

### RE 回复

#### 1. 那 3 个因子命中的条件（RE 用真实行情实测复核）

RE 在 2020-01 ~ 2026-10、5947 个标的上复现了三个因子，**命中的不是同一个条件**：

| 因子 | 命中条件 | 实测证据 | 根因 |
|---|---|---|---|
| `SV02_0002` 历史收盘价现价比 | **条件 4**（横截面零方差） | 非空率 87.3%，但**取值数 = 1** | 注册默认 `window=0` → `close.shift(0)/close` 恒等于 1.0 |
| `SV06_0004` 历史成交量现量比 | **条件 4** | 非空率 82.9%，取值数仅 28 | 同为 `window=0` → `volume/(volume+ε)`，浮点抵消后分母为 0 |
| `SV09_0008` Alpha#096 | **条件 3**（有效样本不足） | **非空率 0.000**（因子全空） | `ts_argmax` / `decay_linear` 遇 NaN 即返回 NaN，13 宽窗口全非空的概率 `0.66^13 ≈ 0.44%`，再套 14 宽衰减后归零 |

**结论：前两个是配置/因子库问题，第三个是因子实现与数据缺失结构的问题**——都不是取数失败。

#### 2. RE 的归类决定：不属失败，改为在响应里给出原因

RE **不把「IC 不可用」标为 `status: failed`**。理由：这三个回测**本身是成功的**——分组曲线、
`quantile_metrics`、净值都照常产出（`SV02_0002` 的各分位年化仍有区分度）。IC 无定义是
**因子或数据的性质**，标 failed 会把可用结果一起藏掉，反而更糟。

改为在 `factor_analysis.definition` 上新增 **`ic_unavailable_reason`**：

| 取值 | 含义 |
|---|---|
| `null` | IC 正常可用 |
| `missing_inputs` | 因子值或远期收益缺失 |
| `no_common_axis` | 因子值与远期收益没有共同日期或标的 |
| `insufficient_cross_section` | 没有任何交易日满足 ≥ 2 个有效样本（因子基本无值） |
| `zero_cross_sectional_variance` | 有样本，但逐日相关系数全不可计算（横截面无方差，例如因子恒为常数） |

对照上面三个因子：`SV02_0002` / `SV06_0004` → `zero_cross_sectional_variance`；
`SV09_0008` → `insufficient_cross_section`。前两者多与取数或配置有关，后两者是因子或数据的
性质，可据此决定是否排查。

#### 3. 顺带修掉的因子库问题

1. **`SV02_0002` / `SV06_0004` 的默认参数退化**：`window` 由 `0` 改为 `5`（与库内其它带窗口
   因子的通行默认一致）。改后实测取值数 **1 → 690 万**、**28 → 804 万**，IC 均可计算
   （`ic_mean` 分别 `-0.0099` / `+0.0044`）。
   ⚠️ **这两个因子的历史回测结果会变**——此前它们是常数，等于没有信号。
2. **`SV09_0008` 不改全局**：RE 用同一条链路验证了 `SV09_0004` / `SV09_0009`，二者**是正常的**
   （非空率 0.78 / 0.81，1600 天有方差），说明不是「用了 `ts_argmax` 就废」。改
   `ts_argmax` / `decay_linear` 的 NaN 策略会波及 **9 个 `ts_argmax` 因子 + 40 个
   `decay_linear` 因子**的结果，风险远大于收益，因此保持现状。

#### 4. SVQuant 侧待办

- **接线 `map_yg_response`**：改用 `factor_analysis.definition.ic_unavailable_reason` 定性，
  不再依赖「`ic_series` 为空」这个只能检出、无法区分的信号。
- **面板展示**：`ic_unavailable_reason` 非 `null` 时 IC 列显示「—」并附原因提示（与「计算失败」
  的失败态区分开）。
- 该字段是**加成变更**，老响应没有这个键，读取时按 `null`（= 正常）兜底即可。
