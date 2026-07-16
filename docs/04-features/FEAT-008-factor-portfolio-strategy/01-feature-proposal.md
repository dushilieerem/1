# 结构化因子组合策略：Feature Proposal

## 背景

现有因子回测只支持单因子和平台固定的组合构建，现有策略回测则要求用户手写完整的 `generate_signals()`。两者之间缺少一种适合大多数研究员、可读且可校验的多因子组合策略表达。

## MVP

用户在 `FactorPortfolioStrategy` 子类中用 `@factor` 编写与因子回测相同的面板因子函数，用唯一 `@signal` 函数通过 Python 运算组合因子；系统支持 `TopN`、`EqualWeight`、`EveryNTradingDays` 并复用现有向量化后端。

不做：事件驱动回测、行业/单票约束、因子资产持久化、Python AST 沙箱或任意权重器。

## 价值

用户看到 Python 而非 YAML；平台仍可识别策略的结构化组件，并保持因子研究的快速向量化执行能力。
