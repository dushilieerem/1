# Technical Design：WorldQuant Alpha 101 因子库迁移

## 1. 模块边界

```text
Factor/libraries/worldquant_alpha101.py
  └─ WorldQuantAlpha101Library（FactorLibrary）
       ├─ alpha001 … alpha101
       └─ 面板算子：rank / delay / delta / ts_rank / correlation / decay_linear …
ResearchEngine FactorLoader
  └─ 动态加载并注册 101 个方法因子
ResearchEngine API
  └─ 按 Factor/libraries/index.yaml 登记加载 worldquant_alpha101
```

QuantCore 继续只负责通用 `Panel`、因子基类和计算后端；公式库不把行业、数据源或回测逻辑写入 QuantCore。

## 2. 算子与计算口径

- 截面算子：按日期对标的横截面做百分位 `rank` 和 `scale`。
- 时序算子：按每个标的滚动计算 `sum`、`stddev`、`min/max`、`argmin/argmax`、`ts_rank`、`product`。
- 关系算子：使用 Pandas rolling `corr/cov`。
- 衰减算子：使用从当前日到窗口起点权重 `d, d-1, …, 1` 的线性加权均值。
- 条件表达式：转换为保持索引和列对齐的 `DataFrame.where`。
- 除零：除数为零的位置返回缺失值；Alpha 101 明确的 `+0.001` 保留原公式常数。

## 3. 数据契约

| 字段 | 用途 | 级别 |
|---|---|---|
| `open/high/low/close/volume` | 核心价格、成交量和收益计算 | 必须 |
| `amount` | 优先作为日成交额和 VWAP 分子 | 可选但推荐 |
| `vwap` | 直接作为成交量加权均价 | 可选 |
| `cap` / `total_mv` | Alpha 56 的市值输入 | 可选，缺失时为样本近似 |
| `sector/industry/subindustry` | Alpha 48、58–70、79–100 的分类中性化 | 可选，缺失时截面去均值 |

## 4. 兼容、回滚与接口影响

- 在 `Factor/libraries/index.yaml` 登记 `worldquant_alpha101` 及 101 个因子元数据和依赖说明；不再维护独立的 API 库名名单。
- 若新库出现问题，从 `Factor/libraries/index.yaml` 移除对应库条目即可停止 API 发现与调用，旧库和其他内置库不受影响。
- API 使用示例：

```json
{
  "library_name": "worldquant_alpha101",
  "factor_name": "alpha101"
}
```

## 5. 关键风险

1. 论文中的 `adv`、VWAP、行业分类与用户数据源可能存在口径差异；通过字段优先级、索引说明和 `implemented` 状态显式披露。
2. 部分长窗口因子计算成本较高；继续使用现有按因子按需计算模型，不预先引入新缓存或并行抽象。
3. 缺少分类字段时的截面去均值不是原始行业中性化；必须在生产数据目录中补齐分类字段后再做同源回归验证。
