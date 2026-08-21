# Technical Design：AI 自然语言向量化策略生成 API

实现位于 `ResearchEngine/app/api/ai_strategy.py`，作为 SaaS AI 服务落地前的受控过渡层。它复用火山方舟 OpenAI 兼容调用方式，但不改变 `app.quantcore` 或回测编排。

```text
Web → 能力预检 → /api/ai/strategy-generations → LLM → JSON → AST/compile → 草稿
                                                              ↓ 用户确认
                                                   /api/backtest/strategy
```

Pydantic 定义独立的请求、响应与草稿模型；内存幂等记录按策略端点隔离。模型调用前先进行能力预检：明确请求成交量/基本面、事件订单、多空或 numpy/TA-Lib 等外部库时直接拒绝，避免模型悄悄改写语义后返回成功。AST 检查默认拒绝，只允许 pandas 别名导入、单个策略类、固定构造函数、固定生成方法和安全表达式。为支持“每 N 日调仓”，允许安全的算术取模、切片、`ffill`、布尔矩阵的 `astype` 和按行除法 `div`；提示词内置 TopN 调仓与均线信号等权的完整无循环模板。静态通过仅代表契约合规，生产回测仍须在无网络、资源受限的隔离环境运行。

回滚方式：移除路由即可停止新入口，不影响因子生成和既有策略回测。
