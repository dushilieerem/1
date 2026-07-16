# Portfolio Backlog

> Initiative 和 Feature 的统一状态入口。状态定义见 `../01-workflow/文档更新规则.md`。

## Initiatives

| ID | 名称 | 优先级 | 状态 | 目标阶段 | 说明 |
|----|------|--------|------|----------|------|
| INIT-001 | 投研核心 | P0 | 开发中 | Wave 1 | QuantCore + ResearchEngine 最小研究闭环 |
| INIT-002 | 交易执行 | P1 | 待分析 | Wave 2 | 模拟盘、组合风控与实盘执行 |
| INIT-003 | 用户、社区与 AI SaaS 平台 | P1 | 待分析 | Wave 3 | 用户、权限、资产隔离、社区、AI、Web 与商业化能力 |
| INIT-004 | 投研能力 Phase 2 | P0 | 待决策 | Wave 1 | 因子预处理、测试和 AI 研究增强 |

## Features

| ID | 名称 | 所属 Initiative | 所属能力 | 优先级 | 状态 |
|----|------|-----------------|----------|--------|------|
| FEAT-001 | QuantCore 核心基础设施 | INIT-001 | 数据/因子/回测/指标 | P0 | 已完成（基础版） |
| FEAT-002 | ResearchEngine 研究服务 | INIT-001 | 策略研究 | P0 | 已完成（基础版 + 因子分析 API 增量） |
| FEAT-003 | 回测适配层 | INIT-001 | 策略回测 | P0 | 已完成 |
| FEAT-004 | 因子资产目录与回测结果缓存 | INIT-001 | 因子研究/研究基础设施 | P0 | 已完成 |

## 维护要求

- 新 Initiative 或 Feature 获得编号时立即登记。
- 状态变化时同时更新本表与对应 Feature README。
- 标记已完成前必须具备 Verification；历史已交付能力允许标记“已完成（基础版）”并在后续补验收记录。
