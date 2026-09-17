# 功能文档

本层回答“系统具体做什么、做到什么程度”：每个 `FEAT-*` 功能包是单个功能从价值到验收的唯一交付工作单元。

## 功能包结构

默认单文件：

```text
FEAT-xxx-功能名称/
└── README.md    # 状态与回链 / 价值与范围 / 业务规则与场景 / 方案设计 / 验收与证据 / 计划与状态
```

内容量大时才拆分子文件（模板与拆分约定见 [FEAT功能包模板](../00-文档治理/文档模板/FEAT功能包模板.md)）：`requirements.md`（业务规则与验收）、`technical-design.md`（技术设计）、`verification.md` / `交付记录.md`（验证与交付证据）、专项参考文档（字段字典、目录清单、API 文档等）。历史包中带数字前缀的文件（如 `02-product-requirements.md`）为当时交付的历史命名，予以保留；**新包不再使用数字前缀，也禁止为凑层写空壳文件**。

## 功能包清单（根目录）

| 包 | 状态 | 主题 |
|----|------|------|
| [FEAT-003-回测适配层](FEAT-003-回测适配层/README.md) | 已完成 | Native 向量化策略回测统一契约 |
| [FEAT-010-投研数据底座](FEAT-010-投研数据底座/README.md) | 待批准 | 点时财务、复权、交易状态与市场基准数据契约 |
| [FEAT-018-自定义证券池与组合基准](FEAT-018-自定义证券池与组合基准/README.md) | 开发中 | 版本化研究资产与快照契约 |
| [FEAT-024-iFinD数据存储](FEAT-024-iFinD数据存储/README.md) | 已批准 | 业务域宽表规范与渐进替换 |
| [FEAT-025-免费数据源基本面与状态MVP](FEAT-025-免费数据源基本面与状态MVP/README.md) | 待批准 | BaoStock/CNINFO 补齐估值与状态 |
| [FEAT-030-因子回测流程重构](FEAT-030-因子回测流程重构/README.md) | 开发中 | 五引擎应用管线与 services/models 分层 |
| [FEAT-031-iFinD采集项目拆分](FEAT-031-iFinD采集项目拆分/README.md) | 已完成 | 采集能力迁入独立 IFind 项目 |
| [FEAT-032-日终模拟盘](FEAT-032-日终模拟盘/README.md) | 待批准 | 日频 VWAP 批量模拟与 ResearchEngine/WebApp 交接契约 |

已废弃的 FEAT-001（QuantCore）归档于 [`99-历史归档/`](../99-历史归档/)。

## 文档归属

| 归属 | 文档位置 | 说明 |
|------|----------|------|
| ResearchEngine | [`ResearchEngine/docs/03-功能文档/`](../../ResearchEngine/docs/03-功能文档/) | 研究服务、因子/策略、API、批量回测和 AI 研究能力 |
| 项目级及跨模块 | 当前目录 | MarketData、跨模块契约和共享能力 Feature |
| WebApp | [`WebApp/docs/`](../../WebApp/docs/README.md) | WebApp 团队维护的前端工程文档；本仓库不创建交接副本 |

## 进入实现的最低条件

- 业务场景、分支和异常均有对应功能。
- 功能入口、操作、字段、状态、权限和提示明确。
- 验收标准可映射到业务目标并可独立执行。
- 已完成架构影响评估、任务拆解、测试策略、发布和回滚方案。
- 已满足分级 [Definition of Ready](../00-文档治理/Definition-of-Ready.md)。

## 当前架构修订

[FEAT-030：因子回测流程重构](FEAT-030-因子回测流程重构/README.md) 的主链已实施，按 [ADR-029](../05-技术决策/ADR-029-研究服务采用services与models分层.md) 采用 `services / models / database` 分层；专项验收尚未全部关闭，状态以功能包和验证记录为准。
