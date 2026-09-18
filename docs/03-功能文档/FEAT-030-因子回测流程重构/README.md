# FEAT-030：因子回测服务集成

- 状态：ResearchEngine 内部实现已迁出；SVQuant 侧保留网关集成
- 所属 Initiative：INIT-001 投研核心
- 所属能力：因子研究
- 优先级：P0

## 目标

ResearchEngine 独立负责因子目录、行情读取、因子计算、回测任务和结果生成。SVQuant 负责用户
鉴权、请求参数和用户资产快照，调用 ResearchEngine HTTP API，并向页面展示结果。

~~~text
用户配置
  → SVQuant backend 鉴权和快照解析
  → ResearchEngine 因子回测 API
  → 任务状态/结果
  → SVQuant 展示与可再生缓存
~~~

## SVQuant 侧范围

- 维护因子目录同步缓存和用户自定义因子元数据。
- 维护因子检测/回测 BFF，适配异步任务、轮询、超时和错误映射。
- 维护用户证券池、组合基准、权限和产品层历史记录。
- 通过网关测试请求转换和与指定 ResearchEngine 版本的集成。

## ResearchEngine 侧范围

因子执行管线、数据 release、因子/策略资产、任务调度、计算测试、API 契约和结果 SQLite 均由
[ResearchEngine 独立仓库](https://gitee.com/yanggu-yuanqi-intelligence/research-engine)维护。
SVQuant 不再保存或运行该服务的 Python 实现。

## 跨仓库契约

- SVQuant 只发送经过鉴权的日期、因子引用、参数和不可变资产快照。
- ResearchEngine 负责校验因子、数据 manifest、版本/哈希和计算参数。
- 异步提交必须通过任务状态确认终态；结果失败、取消、超时和服务不可达都要显式返回。
- SVQuant 不读取 ResearchEngine 的本地行情或结果 SQLite。
- ResearchEngine 与 SVQuant 必须锁步发布；接口变化先更新 ResearchEngine 契约测试，再同步
  SVQuant BFF、前端文案和集成验证。

## 验收

ResearchEngine 的计算和契约测试在其独立仓库执行。SVQuant 侧验收关注：

1. 未登录或无权限请求不会到达 ResearchEngine。
2. 用户资产快照经过版本、归属和内容哈希校验后才提交。
3. 网关能正确处理提交、轮询、终态结果和错误映射。
4. ResearchEngine 不可用时页面显示明确的服务不可用状态，不回退到本地隐式计算。

原 ResearchEngine 内部实现说明和测试记录已从 SVQuant 移除，历史版本仍可通过 Git 历史追溯。
