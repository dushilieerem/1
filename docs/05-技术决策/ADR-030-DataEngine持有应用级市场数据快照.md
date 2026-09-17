# ADR-030：DataEngine 持有应用级市场数据快照

## 问题

此前 `ExperimentManager` 通过 `ResearchRuntime` 创建 Provider、DataEngine 和字段缓存，导致调度、
数据生命周期与回测执行三种职责耦合；也无法明确进程级数据对象的所有者。

## 选择

FastAPI 应用在 `app.state.data_engine` 保存并通过 `DataEngine.get_instance()` 注册进程唯一
DataEngine。lifespan 启动时由它加载当前 MarketData release；字段仅在任务按 spec 的日期范围
请求时读取。关闭时先停止批量协调与 Manager，再关闭 DataEngine。

ExperimentManager 只维护 FIFO、并发、去重、取消和任务状态。Experiment 不再接收伪数据上下文；
因子回测通过全局 DataEngine 的 `get_task_panels()` 获得私有 DataFrame 切片。

## 备选方案

- 继续由 Manager 持有 ResearchRuntime：数据与调度生命周期继续耦合，放弃。
- 模块级静态单例：测试和多应用实例难以隔离，放弃。
- 每个 Experiment 创建 DataEngine：重复读盘且内存不可控，放弃。

## 后果

- 删除 `ResearchRuntime` 与进程全局字段缓存入口。
- 一个 Uvicorn worker 对应一份完整行情快照；切换 release 通过重启或创建新的应用实例完成，运行中任务不会看到磁盘后的数据变化。
- Provider 仍是数据来源适配器，FieldFrameCache 的所有权属于 DataEngine。
