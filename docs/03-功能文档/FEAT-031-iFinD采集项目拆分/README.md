# FEAT-031：iFinD 采集项目拆分

- 状态：已完成
- 所属 Initiative：INIT-001 投研核心
- 所属能力：数据 / 研究基础设施
- 优先级：P0
- 决策：将全部数据生产能力与非活动数据迁入独立 `IFind` 项目，SVQuant 只保留字段/API 展示适配

> 后续边界修订（2026-09-17）：marketdata 已移出 SVQuant，作为 ResearchEngine 部署侧的外部
> 数据目录；`data_manifest.yaml` 和 `quality_report.json` 由数据发布方生成并由 ResearchEngine 校验。

## 为什么做

SVQuant 的核心运行时是研究计算，但原仓同时持有第三方数据源凭据边界、HTTP 采集实现和运维命令，导致发布节奏、依赖和故障域混在同一仓库。拆分后，数据运维可以独立安装、测试和调度 iFinD 管道，ResearchEngine 继续稳定读取已发布数据。

不做的影响：供应商接口变更或采集依赖升级会持续污染投研服务发布；凭据和大体积源数据的责任边界不清；采集失败与研究服务故障难以隔离。

现在做的原因：历史回填、日更、幂等跳过和发布流程已经形成完整闭环，具备按现有行为整体迁移的条件。继续在 SVQuant 内扩展会增加后续拆分成本。

## 目标与指标

- 数据采集、质量发布源码和测试在 SVQuant 中归零，SVQuant 产品层不做任何采集实现。
- 独立项目可在 `svquant` conda 环境中通过 `pip install -e ".[test]"` 安装。
- 历史回填、日更和发布 CLI 均可独立显示帮助并保持原 `data_ingestion.ifind` 内部命名空间。
- 迁移后的全部采集侧自动化测试通过；SVQuant ResearchEngine 不回归。
- 原始数据、候选 release、token 和备份不进入 Git，并全部由 IFind 管理。

## 业务流程

数据运维人员在 `IFind` 项目中完成“配置环境变量 → 历史回填或日更 → 检查 raw/CSV/Parquet → 候选 release → `--dry-run` 校验 → 备份并发布”。任一步失败即停止。ResearchEngine 只读取已发布的 `marketdata/`，不感知供应商接口；SVQuant 只通过 ResearchEngine API 使用研究数据。

## 架构与数据边界

- `IFind` 拥有：供应商凭据、iFinD/AkShare 采集、历史回填、日更、源数据、候选 release、备份、质量校验和发布 CLI。
- ResearchEngine 拥有：部署侧的 `marketdata/` 活动数据、版本/哈希校验、Provider/DataEngine 和研究计算。
- SVQuant 只拥有数据展示所需的 HTTP 适配，不保存活动行情，不通过源码导入或相邻目录推断数据。
- 项目间通过 Parquet、`data_manifest.yaml`、`quality_report.json` 和显式发布目录交接；SVQuant 与 ResearchEngine 通过 HTTP API 交接研究请求和结果。
- 长期决策见 [ADR-031](../../05-技术决策/ADR-031-iFinD采集迁移为独立项目.md) 与 [ADR-032](../../05-技术决策/ADR-032-MarketData扁平只读消费目录.md)。

## 功能范围

MVP 包含 `ifind-data update`、`ifind-data backfill`、AkShare 回填、共享质量工具、候选 release 构建和 `ifind-sync-current`。发布目标必须由 `--target-root` 或 `IFIND_TARGET_ROOT` 指定；默认源数据、release 和备份目录归独立项目所有。

明确不做：不修改 SVQuant 产品 API；不改变 Parquet 字段口径；不新增在线数据服务或调度平台；不在 SVQuant 保留采集兼容入口。

## 投入、收益与优先级

预计投入 1 人日完成仓库拆分、打包、路径解耦、文档和回归。评分为商业价值 3 × 用户价值 4 × 战略价值 5 ÷ 成本 2 = 30，属于高价值低成本，优先级 P0。

收益是采集与研究发布解耦、供应商故障隔离、凭据边界清晰，以及未来独立调度/部署的基础。直接商业收入不单独计量。

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 默认路径变化导致写错目录 | 默认输出归 `IFind/data/ifind`，外部发布目标必须显式配置 |
| 迁移遗漏未提交优化 | 迁移前先刷新 GitNexus 索引并跑基线测试，按文件清单和测试核对 |
| 发布中断影响活动数据 | 保留 `--dry-run`、候选暂存、默认备份和失败恢复 |
| 既有运行时数据体量大 | 同盘移动并按迁移前后文件数与字节数核对；不调用供应商接口改写内容 |

## 验收与回滚

验收要求：独立项目安装成功；iFinD 测试全部通过；CLI 帮助和默认路径正确；SVQuant 不再包含 iFinD Python 实现；保留测试与 ResearchEngine 回归通过；GitNexus 变更只命中预期边界。

回滚时，代码通过两个仓库版本历史恢复；运行时数据由 IFind/ResearchEngine 按上一版发布物或备份恢复，SVQuant 不接收、不重新包装 `marketdata/`，也不应长期恢复采集能力。

## 验收结论与下一步

独立项目安装、67 项采集侧测试、533 项 ResearchEngine 全量回归、实际扁平目录读取、119,790 个源数据文件与 14 个活动文件迁移核对均已通过，交付证据见 [交付记录](交付记录.md)。Feature 状态为“已完成”。

下一步由运维方配置 `IFIND_REFRESH_TOKEN`、`IFIND_OUTPUT_ROOT` 与发布目标，并将调度任务切换到独立项目 CLI；真实供应商调用和正式数据发布不属于本次无凭据代码迁移验收。
