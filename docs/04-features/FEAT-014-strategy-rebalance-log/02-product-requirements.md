# 策略调仓日志：Product Requirements

## 用户故事

作为研究者，我希望在请求策略回测时选择返回调仓日志，以便核验每次调仓的标的和权重变化。

## 业务规则

1. `POST /api/backtest/strategy` 增加可选布尔字段 `include_rebalance_logs`，默认 `false`。
2. 为 `true` 时，响应 `rebalance_logs` 按调仓信号日分组。
3. 每笔记录含 `symbol`、`side`、`previous_weight`、`target_weight`、`weight_change`。
4. 仅返回权重实际变化的标的；权重不变及非调仓日不返回。
5. 未请求时 `rebalance_logs` 为 `null`，既有调用不受影响。
6. 日志为目标权重变更，不承诺是订单或实际成交回报。
7. `include_execution_timeline=true` 时，API 返回供 Web 统一消费的时间线：向量化策略映射为目标权重变更，事件策略映射为订单、成交、账户快照和审计事件。

## 验收标准

1. Native 回测结果包含首建仓和后续调仓的买卖日志。
2. API 未传开关时不返回日志；传入开关时返回结构化日志。
3. 既有策略 API 测试继续通过。
4. 向量化与事件策略均可通过 `execution_timeline` 返回可展示的执行过程。
