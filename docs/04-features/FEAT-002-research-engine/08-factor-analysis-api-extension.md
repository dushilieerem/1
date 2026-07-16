# FEAT-002 增量：因子分析可视化数据 API

> 状态：已完成  
> 最后更新：2026-07-20

## 1. Feature Proposal

### 背景与用户价值

上层前端需要绘制日频 IC、累计 IC、IC 分布、60 日滚动 IR，以及行业与行业内分组收益曲线。当前 `POST /api/backtest/factor` 仅返回 IC 汇总值和全市场分组累计净值，无法支撑这些图表。

ResearchEngine 仍是纯回测计算服务：前端或 AI/应用服务管理因子库、策略库、结果持久化和图表渲染；本服务只接收因子代码和参数，返回一次回测的结构化计算结果。

### MVP 范围

**必须做**：在既有因子回测响应的 `factor_analysis` 中增加 IC 时间序列、累计 IC、60 日滚动 IR、行业等权收益净值、行业内因子分组净值和计算口径元数据。

**明确不做**：返回 PNG/Base64 图表；维护因子库或行业分类主数据；保存研究历史；新增前端接口。

## 2. Product Requirements

### 用户流程

1. 上层服务提交因子代码和回测参数。
2. ResearchEngine 使用指定行情数据和行业映射执行回测与分析。
3. 上层服务消费 `factor_analysis` 的序列字段绘图；IC 分布由 `ic_series[].value` 自行分桶。

### 业务规则

- 日频 IC 是同一交易日横截面中因子值和 `ic_horizon=1` 个交易日远期收益的 Pearson 相关系数；仅使用二者均非空的标的。
- 累计 IC 为日频 IC 的简单累加，不是复利净值。
- 60 日滚动 IR 为最近 60 个有效日频 IC 的均值除以样本标准差（`ddof=1`）；不足 60 个有效观测不返回点。
- 行业收益曲线为行业内全部有效标的的等权日收益固定本金净值（`1 + 日收益累加`）。
- 行业分组曲线为每个行业内按因子从低到高独立分组后的等权日收益固定本金净值；行业可用标的少于分组数时跳过该日，行业全程无有效分组时不返回该行业。
- `stock_info.parquet` 提供 `code -> industry` 映射；文件、字段或有效行业映射缺失时，IC 相关字段仍正常返回，行业字段返回空数组。

### 验收标准

1. 因子回测成功时返回非空 `ic_series`、`cumulative_ic_series`；两者日期逐一对应，累计值等于 IC 简单累加。
2. 60 个以上有效 IC 时返回 `rolling_ir_series`；每个点带窗口大小和样本数。
3. 提供行业映射且至少一个行业样本充足时，返回行业收益曲线和行业分组曲线；分组数遵循请求的 `groups`。
4. 无行业映射时，接口保持 HTTP 200，行业数组为空。
5. 既有响应字段和缓存行为保持兼容。

## 3. Technical Design

### 响应契约

在 `factor_analysis` 增加：

```text
definition: {ic_type, forward_return_days, signal_lag_days, rolling_ir_window,
             groups, industry_return_method, industry_grouping_method}
ic_series: [{date, value, sample_size}]
cumulative_ic_series: [{date, value}]
rolling_ir_series: [{date, value, window, sample_size}]
industry_equity_curves: [{industry_code, industry_name, points:[{date, value}]}]
industry_group_equity_curves: [{industry_code, industry_name,
  points:[{date, groups:{G1:value, ...}}]}]
```

行业代码暂以 `stock_info.parquet` 中的行业字段值为准，同时作为 `industry_code` 与 `industry_name`，不在本服务内维护行业主数据。

### 模块边界与实现

- `researchengine.experiment.Experiment` 在已计算的因子值、收盘价和远期收益上生成分析 DataFrame，不重复读取行情或执行回测。
- `researchengine.api.schemas` 定义 JSON 契约；`researchengine.api.runner` 只进行 DataFrame 到 Pydantic 对象的序列化。
- 不修改 QuantCore 指标接口；序列属于 ResearchEngine 的 API 投影，不改变基础指标的汇总职责。

### 风险、兼容与回滚

- 行业计算按日、按行业、按分组循环，在大股票池下会增加 CPU 时间；MVP 先以正确性为先，并只对存在行业映射的回测执行。
- 新字段均为可选或默认空数组，旧客户端可忽略。若需要回滚，只移除新增字段的消费方；既有字段和回测路径不变。

### 测试策略

构造有 `stock_info.parquet` 的小型行情，验证序列长度、累计 IC 恒等式、滚动窗口、行业曲线和行业分组键；保留无行业文件的既有 API 测试。

## 4. Project Plan

| 任务 | 复杂度 | 风险 | 依赖 |
|------|--------|------|------|
| 补充需求与 API 契约 | 1 | 低 | 无 |
| 计算 IC/滚动 IR/行业序列 | 3 | 中 | 因子值、远期收益、行业映射 |
| Pydantic 模型与序列化 | 2 | 低 | 计算结果 |
| API 回归测试与验证 | 2 | 中 | 测试行情 |

里程碑：M1 契约确认（已完成）；M2 API 与测试通过（已完成）；M3 前端联调。
