# FEAT-012：技术设计

## 模块边界

新增 `QuantCore/quantcore/factor/tool.py`，只包含无状态、数据源无关的 DataFrame 函数。它不依赖 `Panel`，也不访问 MarketData。

`neutralize` 对每一个交易日以截距、行业哑变量和可选的 `log(market_cap)` 做最小二乘回归，返回残差。行业暴露可为日期×标的 DataFrame，或静态的标的 Series；市值必须与因子对齐。

## 兼容性

保留 `FactorPortfolioStrategy` 的静态方法签名，内部委托新工具函数，因此现有策略代码无需改动。

## 测试策略

覆盖去极值边界、缺失值、常数横截面、归一化、行业和市值中性化、非法输入，以及组合策略的兼容行为。
