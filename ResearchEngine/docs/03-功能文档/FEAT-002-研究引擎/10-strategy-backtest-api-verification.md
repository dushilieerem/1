# 策略回测 API MVP 验证记录

- 交付日期：2026-07-20
- 状态：已验证
- 范围：前端提交策略代码，ResearchEngine 同步执行回测并返回结构化结果。

## MVP 契约

前端调用 `POST /api/backtest/strategy`，提交一个且仅一个包含
`generate_signals()` 方法的策略类。策略构造函数接收：

- `factor_values`：前端同时提交 `factor_code` 和 `factor_name` 时为计算后的因子宽表；否则为收盘价宽表，保证策略可在无因子模式下运行。
- `close`：按请求日期范围和股票池过滤后的收盘价宽表。
- `params`：请求中的 `strategy_params`。

`generate_signals()` 必须返回日期 × 标的的 `pandas.DataFrame` 目标权重。ResearchEngine 不自行撮合，统一调用 QuantCore 回测适配层；响应包含标准绩效指标（含累计收益）、净值与回撤、分年收益，以及按需返回的持仓快照。

## 已验证场景

1. 自定义策略代码与自定义因子代码可在同一请求中执行。
2. 策略参数可传入策略构造函数，策略信号进入 Native 回测后端。
3. 响应包含策略类名、股票池、回测后端、绩效指标、净值曲线与持仓快照。
4. 没有 `generate_signals()` 的代码返回 HTTP 200 和业务错误，不产生 500。
5. 未声明的请求字段返回 HTTP 422，防止前端静默传入无效配置。

## 验证命令与结果

```bash
conda run -n svquant python -m pytest ResearchEngine/tests/test_api.py -q
conda run -n svquant python -m pytest QuantCore/tests/test_adapter.py -q
```

结果：ResearchEngine API 17 项测试、QuantCore 回测适配层 14 项测试全部通过。

## 边界与后续工作

- 本 MVP 为同步、进程内可信代码执行；公网部署前必须通过独立 Feature 增加子进程或容器沙箱、资源限额和超时控制。
- 策略资产管理、版本管理、异步任务持久化、鉴权与多租户不属于 ResearchEngine。
- 事件驱动策略与精确 A 股交易规则仍由后续双引擎阶段交付；本版本使用已有的向量化适配层。
