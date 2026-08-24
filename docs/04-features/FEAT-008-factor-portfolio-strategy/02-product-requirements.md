# 结构化因子组合策略：需求规格

## 用户流程

前端提交 `FactorPortfolioStrategy` 源码 → ResearchEngine 加载策略 → 因子函数基于行情面板计算 → `@signal` 输出综合分数 → `TopN` 选股、`EqualWeight` 配权、按调仓周期输出目标权重 → 现有回测后端执行。

## 业务规则

- 策略必须且只能声明一个 `@signal` 方法；它必须返回日期 × 标的的分数宽表。
- `@factor` 方法和因子回测一样可访问 `self.close`、`self.volume`、`self.pe_ttm` 等字段。
- `rank`、`zscore`、`winsorize`、`normalize` 按日横截面计算，用于因子组合前的量纲处理。
- `TopN(n)` 仅选取分数最高的 `n` 个有效标的；`EqualWeight` 对入选标的等权；非调仓日输出 `NaN` 以沿用上一期目标仓位。

## 验收标准

1. 两个 `@factor` 和一个 `@signal` 的策略可经 `/api/backtest/strategy` 成功回测。
2. `@signal` 中的因子函数可相加、相乘并调用标准化函数。
3. 没有或有多个 `@signal` 时返回清晰错误。
4. `TopN`、等权和每 N 日调仓的目标权重符合单元测试断言。
5. 原有 `generate_signals()` 策略 API 与测试不退化。
6. Web 请求传入 `include_rebalance_logs=true` 时，返回按调仓日聚合、仅含权重变化标的的目标调仓日志；未传时不返回该数据。
