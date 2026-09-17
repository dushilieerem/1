# Wave 2 战术设计：实盘交易系统（阶段二）

> 文档版本：v0.1（占位，待 Wave 2 启动前深化）
> 形态：CLI/SDK（无 AI、无 SaaS）
> 对应 Roadmap：阶段二（PRD §10）
> 前置阅读：`../../domain-strategy.md`、`../INIT-001-研究核心/domain-design.md`

---

## 1. 涉及上下文

| BC | 范围 | 深度 |
|---|---|---|
| BC7 Portfolio & Risk | 组合构建 + 风控规则 + 风险指标 | 深做 |
| BC8 Execution / Trading | 券商接入 + 订单 + 实盘持仓 | 深做 |

## 2. 契约兑现点（Wave 1 已预留）

- **`ExecutionEngine` 抽象**（Wave 1 BC3 §3.5）：BC8 实现 `LiveExecutionEngine`，替换 BC3 的 `SimulatedExecutionEngine`，**BC3 回测逻辑零改动**
- **`MarketRule` 共享**：BC8 复用 BC6 的 `MarketRuleProfile`，与回测同一规则源
- **模拟盘 → 实盘**：模拟盘（实时行情驱动 `SimulatedExecutionEngine`）作为实盘前置过渡

## 3. 边界（Wave 1 已确立）

- BC3 回测**内置市场规则约束**（T+1/涨跌停/不超买，来自 BC6）≠ BC7 **业务风控规则**（止损/仓位/禁投）
- BC7 可作为回测的可选风控前置注入，不破坏 BC3 内置不变量

## 4. 接口预留（API-first）

- 订单/风控/组合能力暴露 Python API + CLI + 预留 HTTP 适配层
- 供 Wave 3 AI 平台调用
- **实盘二次确认护栏在 Wave 3 生效**（BC1 `GuardrailDecision=RequireConfirmation`）；Wave 2 为手动操作，无 AI

## 5. 待深化（启动 Wave 2 前）

- [ ] 券商接口适配层（ACL）设计：多券商适配 vs. 单券商首发
- [ ] `Order` 聚合根不变量与状态机（Pending→Submitted→Filled/Rejected/Cancelled）
- [ ] `LivePosition` 与回测 `PositionSnapshot` 的统一模型
- [ ] BC7 `RiskRule` 规则引擎语法（止损/仓位/禁投/行业暴露上限）
- [ ] BC7 `RiskMetrics`（VaR/敞口）计算频率与缓存
- [ ] HTTP 适配层实现时机（Wave 2 是否就实现）

---

*待 Wave 2 启动前，基于 Wave 1 已确立的契约进行战术设计深化。*
