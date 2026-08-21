# ADR-022：回测运行时由 ExperimentManager 持有共享行情上下文

## 状态

已接受（2026-08-19）

## 问题

每日全量因子回测和单因子 API 都会重复使用相同的行情字段。如果每个因子或请求重新
构建 `FieldParquetProvider`、`DataEngine` 并读取 Parquet，1055 个因子的运行时间和
I/O 会线性放大；因子库实例还可能在并发 Worker 间共享可变 `_panel`，产生数据串扰。

## 选择

让 `ExperimentManager` 成为回测任务的统一运行时边界，并持有进程内 `ResearchRuntime`：

- runtime 按 `MarketData/current` release 懒加载一个 `FieldParquetProvider` 和
  `DataEngine`；同一 Manager 下的 CLI、因子 API、策略 API 复用它们；
- Provider 使用带字节上限的字段级 LRU，并以 release、字段和切片组成缓存键；并发
  miss 合并为一次实际读取；
- release 变化时创建新的上下文，旧上下文不再接收新任务；
- Worker 只共享只读行情视图，因子库在计算时复制实例并绑定当前 `Panel`，中间结果
  仍为任务私有；
- 保留 `ExperimentManager.create/run` 的旧调用兼容性，只有显式注入 runtime 的
  回测路径使用共享上下文。

## 备选方案

### 每个请求独立 Provider

实现简单但会重复 I/O、重复解析和重复内存分配，不适合全量因子批处理。

### 全量启动时加载 MarketDataSnapshot

可进一步减少首次 miss，但 Windows 下内存峰值高，且 release 切换需要双份快照；先以
按需 LRU 作为 MVP，再根据 50 个代表因子的耗时和内存基准决定是否升级。

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
