# 示例与常见问题

> 关联：[因子与策略编写指南入口](../07-factor-strategy-guide.md)

## 1. 创建并回测因子

1. 在前端创建因子库，例如“动量因子”。
2. 新建 `momentum_5d` 因子。
3. 填写：

```python
def momentum_5d(self):
    """过去 5 个交易日的收益率。"""
    return self.close.pct_change(5)
```

4. 调用因子回测 API：

```python
import requests

response = requests.post("http://<research-api>/api/backtest/factor", json={
    "factor_code": """def momentum_5d(self):
    return self.close.pct_change(5)
""",
    "factor_name": "momentum_5d",
    "universe": "CSI500",
    "portfolio_type": "long_only",
    "rebalance_days": 20,
    "groups": 5,
    "benchmark": "CSI300",
})
result = response.json()
if result["error"]:
    raise RuntimeError(result["error"])
```

## 2. 常见问题

### 因子值需要手动处理 NaN 吗？

通常不需要。滚动窗口前的 NaN 会由系统在后续分析中处理；不要用未来值填补。

### 一个因子库可以有多个因子吗？

可以。每个因子是同一库文件中的一个方法。

### 策略回测返回 HTTP 200 是否代表成功？

不一定。因子或策略的业务错误会写入响应 `error` 字段；只有 `error: null` 才代表成功。

### 如何通过 API 调用事件策略？

事件策略可以调用同一个 `/api/backtest/strategy` 端点，但必须显式设置
`engine_mode: "event"`。例如：

```python
response = requests.post("http://<research-api>/api/backtest/strategy", json={
    "engine_mode": "event",
    "strategy_id": "donchian_a_share_event",
    "start": "2026-07-01",
    "end": "2026-08-14",
    "include_execution_timeline": True,
})
result = response.json()
if result["error"]:
    raise RuntimeError(result["error"])
```

事件策略必须实现 `initialize(context)`；向量化策略必须实现
`generate_signals()`，两种契约不能混用。

### 我能直接粘贴聚宽策略吗？

不能。SVQuant 不提供 `jqdata`、全局 `g` 或 `run_daily` 兼容层；应按[事件策略规范](03-event-strategy-writing.md)迁移到 `context` 接口。
