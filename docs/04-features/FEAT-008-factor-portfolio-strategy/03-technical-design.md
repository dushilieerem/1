# 结构化因子组合策略：技术设计

新增 `quantcore.backtest.adapter.factor_strategy`：

```python
class FactorPortfolioStrategy(FactorLibrary, IStrategy):
    selector = TopN(30)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(20)
```

`@factor` 和 `@signal` 仅标记方法；执行时把 `Panel` 绑定到 `FactorLibrary`，调用唯一 signal 方法取得分数，再转换为 `BacktestSignals`。不新增第二套因子表达式语言。

ResearchEngine 在策略类为 `FactorPortfolioStrategy` 子类时传入已加载的 `Panel`；其他策略维持现有 `factor_values/close/params` 构造与 `generate_signals()` 契约。该选择保证向后兼容。

测试覆盖信号校验、横截面处理、目标权重、API 端到端和既有 API 回归。回滚方式为移除新策略类的使用；现有端点和后端不变。

策略回测后端基于目标权重矩阵生成统一调仓日志，记录调仓信号日、标的、买卖方向和调整前后权重。ResearchEngine 仅在请求的 `include_rebalance_logs=true` 时把日志返回给 Web，默认不序列化，保持既有响应体大小和兼容性。日志描述目标权重变更，不替代未来事件驱动引擎的订单/成交回报。
