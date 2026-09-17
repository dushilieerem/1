# ADR-022：回测运行时由 ExperimentManager 持有共享行情上下文

## 状态

已被 ADR-030 替代（2026-08-28）

> 历史记录保留。当前实现由 FastAPI 应用持有 DataEngine，ExperimentManager 只负责调度；
> 详见根目录 `docs/05-技术决策/ADR-030-DataEngine持有应用级市场数据快照.md`。

## 问题

因子批量回测和单因子 API 都会重复使用相同的行情字段。如果每个因子或请求重新
构建 `FieldParquetProvider`、`DataEngine` 并读取 Parquet，1055 个因子的运行时间和
I/O 会线性放大；因子库实例还可能在并发 Worker 间共享可变 `_panel`，产生数据串扰。

## 选择

让 `ExperimentManager` 成为回测任务的统一运行时边界，并持有进程内 `ResearchRuntime`：

- FastAPI lifespan 启动时创建活动 `MarketData` release 的 `FieldParquetProvider`
  和 `DataEngine`，并预热全部研究字段；同一 Manager 下的因子 API 复用它们；
- Provider 使用无容量上限的进程级字段快照，只缓存完整字段；任务切片不进入缓存。因子任务
  首次访问字段时从快照切片并深拷贝，确保任务间不共享可修改 DataFrame；
- release 变化时创建新的上下文，旧上下文不再接收新任务；
- Worker 只共享只读行情视图，因子库在计算时复制实例并绑定当前 `Panel`，中间结果
  仍为任务私有；
- 保留 `ExperimentManager.create/run` 的旧调用兼容性，只有显式注入 runtime 的
  回测路径使用共享上下文。

## 备选方案

### 每个请求独立 Provider

实现简单但会重复 I/O、重复解析和重复内存分配，不适合全量因子批处理。

### 按需字段 LRU

已被当前选择替代。它降低开发机内存压力，但会把 Parquet I/O 带入请求热路径，且无法形成
明确的“活动 release 全量只读快照”所有权。服务器部署以内存容量换取稳定的请求时延；新
release 通过启动新实例、完整预热后切流，不在旧进程中热替换。

### 多进程共享快照或外部缓存

Linux fork/COW、Ray Object Store 或 Arrow Flight 适合更大规模部署，但会引入部署和
运维复杂度；当前任务计划 + 本地研究服务不需要这些依赖。

## 后果

正面：同一进程内的行情读取和引擎构建显著减少，CLI/API 的数据口径统一，release 切换
具有明确边界；并发因子不会互相覆盖 `_panel`。

负面：缓存占用受进程内上限约束，首次访问字段仍有读取成本；DataFrame 视图必须遵守
只读约定；跨进程 API worker 之间仍各自拥有一份 runtime。

## 迁移条件

当需要跨进程共享物理内存、多机回测、分钟/Tick 数据，或字段缓存命中率和内存峰值达到
瓶颈时，再评估完整只读快照、Linux fork/COW、PostgreSQL/ClickHouse 或专用数据服务。
