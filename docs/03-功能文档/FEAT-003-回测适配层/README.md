# FEAT-003：回测适配层

> 当前边界：ResearchEngine 已迁出 SVQuant；本文只记录 SVQuant 产品层通过 HTTP 使用回测能力的约束。
> ResearchEngine 的内部实现、API 契约和契约测试以[独立仓库](https://gitee.com/yanggu-yuanqi-intelligence/research-engine)为准。

> 范围演进已实施：[FEAT-030](../FEAT-030-因子回测流程重构/README.md) 负责因子回测网关，
> 本 Feature 保留策略回测的产品侧适配和验收。

- 状态：已完成
- 所属 Initiative：INIT-001 投研核心
- 所属能力：策略回测
- 代码位置：ResearchEngine 独立仓库内部；SVQuant 仅通过 HTTP API 使用策略回测。

## 目标

通过统一 HTTP 契约为策略回测接入 ResearchEngine；因子回测由 FEAT-030 的网关流程使用。

## 文档索引

- `03-technical-design.md`：适配层详细设计和使用方式。

## 文档缺口

该 Feature 在新工作流建立前已完成；ResearchEngine 内部实现和计算验证不在本仓库重复维护。
