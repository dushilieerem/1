# 策略调仓日志：Technical Design

## 模块边界

`QuantCore.backtest` 从 `BacktestSignals.target_weights` 生成统一日志并存入 `BacktestResult.rebalance_logs`。NativeEngine 复用该生成逻辑。`ResearchEngine.api` 只负责按请求开关序列化。

`ResearchEngine.api` 同时提供按需的 `execution_timeline` 兼容层。向量化模式将 `rebalance_logs` 映射为 `type=rebalance`；事件模式按时间合并订单、成交、账户快照和审计事件。该字段不改变既有 `rebalance_logs` 语义，供 Web 作为唯一展示数据源。

## 数据规则

目标权重前向填充后与前一日有效目标权重比较。差值大于零为 `buy`，小于零为 `sell`；每条日志记录调整前后权重及差值。时间为策略产生目标权重的信号日。

## 兼容与回滚

请求字段默认关闭，响应新增可空字段，旧客户端兼容。出现问题时可停用 `include_rebalance_logs`，不影响回测计算、指标或持仓快照。

## 测试策略

单元测试验证首次建仓及换仓方向；API 测试验证按需返回和默认空值。
