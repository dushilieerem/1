# Product Requirements：AI 自然语言向量化策略生成 API

## 用户流程

```text
自然语言假设 → POST /api/ai/strategy-generations → 受控策略草稿
                                                    ↓ 用户审阅确认
                                      POST /api/backtest/strategy
```

## 业务规则与验收

1. 请求含 `prompt`、可选 `universe`/`frequency`/`preferred_strategy_name` 和 UUID `idempotency_key`；频率仅为 `1d`，未知字段返回 `422`。
2. 成功响应返回一个策略类源码、策略类名、说明、字段、假设、警告和校验状态；相同幂等键与内容不得重复调用供应商，不同内容返回 `409`。
3. 草稿必须是一个自由向量化策略类，含 `__init__(self, close)` 与 `generate_signals(self)`；后者返回“日期 × 标的”的 pandas `DataFrame` 目标权重。
4. 仅允许 `import pandas as pd`、`self.close`、白名单面板方法、局部计算及 `pd.DataFrame`；允许安全的算术取模和切片，以表达固定周期调仓；禁止其他 import、动态执行、双下划线属性、文件和网络访问。
5. 请求明确要求当前能力目录之外的数据字段、事件订单、多空或外部计算库时，服务在调用模型前返回 HTTP 200 与 `rejected`，并说明不支持的能力；不得以不等价的 close 策略冒充成功。
6. 静态校验或 JSON 解析失败返回 HTTP 200 与 `rejected`，不返回 `strategy`；错误须包含被拒绝的方法或结构；不会执行或自动回测代码。

验收：合法模型响应为 `ready` 且可编译；不安全源码为 `rejected`；幂等与冲突行为符合规则；生成代码可原样作为 `strategy_code` 提交至既有回测 API。
