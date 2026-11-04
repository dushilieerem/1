# 流程版的已有能力复用清单

2026-11-04。原则：先查已有 API 和服务；数据契约不匹配时做适配，不另造同类计算引擎。业务层不能直接导入 ResearchEngine 的 Python 实现，所有计算经 HTTP 边界。

| 能力 | 当前复用位置 | 机构流程版新增内容 |
| --- | --- | --- |
| 真实行情查询 | sunvalley-data 的发布版本 /state 与 /query | 固定发布 ID、日期范围、字段面板适配和内容摘要；暂缓采集治理 |
| 因子算子 | ResearchEngine app/services/factor/tool.py | 受限表达式语法与白名单，不允许运行任意模型生成 Python |
| 截面 IC / Rank IC | MetricEngine._factor_statistics | T+1 开盘标签、研发分段清除跨界标签、报告适配 |
| 因子分层 | portfolio/grouping.py 的 rank_groups | 高低因子层的前瞻收益诊断；不作为交易净值 |
| 信号生成 | 既有 rank、zscore、winsorize | 固定因子版本与权重解析 |
| 策略持仓构建 | PortfolioEngine.build | 将受限表达式组合为信号矩阵，传递 next_open 与持仓参数 |
| 回测与成本 | MetricEngine.evaluate | 传入固定发布面板与统一成本，整理真实返回收益，不编写撮合逻辑 |
| 风险与收益指标 | MetricEngine.calculate | 展示字段、完整报告和源码摘要 |
| 组合研究 | 既有 MetricEngine 指标能力 | 对已生成策略净收益按固定权重混合，保留现金和日期对齐检查 |
| 任务与审核 | 原有 workflow_workspace 的异步工具、SQLite Store、人工审核 | 新增任务 revision、并发冲突、幂等、候选筛选、冻结版本 |
| 模型连接 | 原有 Agent 的 DeepSeek 连接、预算预留、调用及工具轨迹 | 按当前步骤开放工具、建议字段、人工采纳及版本防覆盖 |

## 已核对的标准回测 API

- ResearchEngine POST /api/backtest/factor：接受 factor_code 或 library_name / factor_name；使用已有数据目录 / DataEngine，支持证券池快照。
- ResearchEngine GET /api/backtest/factor/{run_id} 和 DELETE 同路径：查询和取消标准因子回测。
- ResearchEngine POST /api/backtest/strategy：接受策略代码或策略 ID，提供向量化及事件模式；使用已有 ExperimentManager / DataEngine。

这些 API 目前没有 sunvalley-data 发布版本 data_version 的请求字段，也不直接接收本版冻结的多表达式配置。因此本期 **没有声称已直接调用这些标准回测路由**，而是在同一个 ResearchEngine 仓库新增 workflow_tools HTTP 适配入口，连接固定版本数据并复用上述计算组件。未修改或复制已有 PortfolioEngine / MetricEngine 源码。

这不是新增另一套回测引擎。后续在标准 API 支持发布快照与受限表达式契约后，优先把 workflow_tools 适配到标准 API；不能让浏览器或模型直接提交任意 Python 绕过既有沙箱。

## 不重复建设的功能

事件撮合、实盘订单、账户仓位、税费细分、证券池管理、因子 / 策略标准目录、企业身份都应继续沿用平台已有服务或其接口。当前固定样本研究入口没有这些能力，不提供会误导用户的启用开关。

## 当前部署边界

真实服务器研发环境，回环端口加 SSH 隧道访问；内部研究任务使用隔离 SQLite。尚未把这个入口嵌入主 React 路由、企业统一身份或生产数据库。正式对外部署前需完成这些接口集成与权限验收，不能把能运行的研究链路描述成完整生产平台。
