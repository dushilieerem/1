# ADR-032：MarketData 采用扁平只读消费目录

> 当前修订（2026-09-07）：本文原决策的 `MarketData/` 消费目录已废弃。ResearchEngine
> 现在默认只读仓库根目录下的 `marketdata/` iFinD 目录镜像；下文保留原决策作为历史记录。

## 问题

SVQuant 的 `MarketData` 同时容纳 `current`、`sources`、`releases`、`backups` 和 `DataIngestion`，让研究运行时既像数据消费者又像数据生产系统。即使 iFinD 代码先行拆分，免费源、共享发布工具和大体积非活动数据仍使边界含混。

## 选择

SVQuant 的 `MarketData/` 根目录直接作为唯一活动数据目录，只保留 `benchmark`、`calendar`、`display`、`metadata`、`panels`、`universe`、清单和质量报告。删除 `current/` 包装层。

全部数据采集代码、测试、原始数据、候选与历史 release、发布暂存和回滚备份由 `D:\project\IFind` 管理。IFind 通过显式 `--target-root D:\project\SVQuant\MarketData` 发布；SVQuant 只读消费，不感知供应商与生产过程。

## 备选方案

1. 保留 `MarketData/current`，只迁出采集代码：目录仍暴露生产侧 sources/releases/backups 的历史惯性，边界不彻底。
2. 在 SVQuant 中保留免费源与质量工具：仍会引入采集依赖、运维入口和写权限，不符合纯消费者定位。
3. 让 ResearchEngine 直接读取 IFind release：会把研究运行时与采集项目目录结构耦合，降低独立部署能力。

## 后果

正面后果：SVQuant 数据边界单一、部署配置更简单，供应商依赖与凭据彻底隔离；IFind 可以独立调度、回滚和扩展数据源。

负面后果：发布工具必须显式管理 IFind 内的候选与备份；依赖旧 `MarketData/current` 的脚本和文档需要更新。`FieldParquetProvider` 暂时保留旧包装层兼容，但新部署和文档不得继续使用该结构。
