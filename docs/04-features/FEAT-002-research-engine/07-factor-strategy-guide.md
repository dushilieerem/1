# 因子与策略编写规范

> 文档版本：v2.0
> 最后更新：2026-07-29
> 适用平台：SVQuant ResearchEngine v2.0

本指南已按工作内容拆分。请按需要阅读对应规范，而不是在一个长文档中混合因子、向量化策略和事件策略的接口。

| 文档 | 适用场景 |
|------|----------|
| [01-因子编写规范](07-factor-strategy-guide/01-factor-writing.md) | 创建、编辑和回测因子；字段、模板与最佳实践 |
| [02-向量化策略编写规范](07-factor-strategy-guide/02-vectorized-strategy-writing.md) | 因子选股、Top-N、目标权重、`/api/backtest/strategy` |
| [03-事件策略编写规范](07-factor-strategy-guide/03-event-strategy-writing.md) | 突破、止损、持仓状态、订单与 A 股日频规则 |
| [04-示例与常见问题](07-factor-strategy-guide/04-examples-and-faq.md) | 从创建因子到调用 API 的完整示例、常见错误 |
| [05-前端因子库映射](07-factor-strategy-guide/05-frontend-factor-library.md) | 前端/后端对因子库文件与模板的映射 |

策略选择原则：只需生成日期 × 标的目标权重时写向量化策略；需要订单、持仓状态、T+1、停牌或涨跌停时写事件策略。两种接口不能混用。
