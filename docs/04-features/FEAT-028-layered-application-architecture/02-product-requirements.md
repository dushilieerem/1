# Product Requirements：ResearchEngine 分层应用架构

## 用户故事

1. 作为 API 使用者，我希望所有请求经过 `/api` 控制器并得到稳定的请求/响应结构。
2. 作为研究员，我希望因子和策略只依赖 QuantCore 的公开接口，不被 FastAPI 运行时绑架。
3. 作为平台维护者，我希望 FastAPI 进程只创建一个 Manager 和一个行情运行时。
4. 作为批量任务使用者，我希望批量回测最多同时提交两个因子；一个结束后才补充下一个。
5. 作为交互式用户，我希望已经排队的交互回测按普通 FIFO 先于后提交的批量任务执行。

## 业务边界

- API 只负责参数校验、依赖注入、业务调用和 schema 序列化；
- 业务协调器负责用例、幂等、重试、进度和状态转换；
- repository/database 负责 SQLite、资产目录和结果持久化；
- QuantCore 只负责数据、因子、指标和回测基础设施；
- `Experiment` 只接受 Manager 注入的只读 `ExperimentContext`；
- 生产只支持单实例、单 Uvicorn Worker，内部批量接口只部署在可信内网。

## 验收标准

- `from app.main import app` 可导入，lifespan 能启动并关闭 Manager；
- `Experiment` 不能直接实例化，Manager 拒绝普通 callable；
- FactorExperiment、StrategyExperiment 能通过 Manager 执行；
- 任意时刻批量未完成提交数不超过 2，完成一个才提交下一个；
- Manager 的任务执行顺序与提交顺序一致，不根据 lane 插队；
- API 层无直接 QuantCore/SQLite 导入，QuantCore 无 FastAPI/service/schema 导入；
- 旧教学入口、旧包导入和旧式实验构造工作流不再存在；
- editable 安装、启动 smoke test 和全量 pytest 通过。
