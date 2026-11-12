# 回测服务集成与执行边界

> 本文只描述 SVQuant 如何使用 ResearchEngine 的回测能力。
> ResearchEngine 内部引擎、任务状态、数据 Provider 和结果存储的详细设计以独立仓库为准：
> https://gitee.com/yanggu-yuanqi-intelligence/research-engine

## 1. 设计目标

SVQuant 负责把用户意图变成经过鉴权和校验的研究请求，再把 ResearchEngine 的结果转换成
产品可展示的数据。回测计算、行情读取、策略执行和结果持久化全部属于 ResearchEngine。

~~~text
页面操作
  → SVQuant backend 鉴权/校验
  → HTTP 网关
  → ResearchEngine 计算
  → HTTP 响应
  → SVQuant 展示/缓存
~~~

SVQuant 不在本地保留一套备用回测引擎。ResearchEngine 不可用时，系统返回可识别的失败状态，
由用户重试或按人工运维流程处理。

## 2. SVQuant 侧组件

| 组件 | 位置 | 责任 |
|------|------|------|
| ResearchEngine 网关 | backend/app/routers/re_gateway.py、backend/services/core/re_http_gateway.py | 统一转发、超时和错误映射 |
| 因子回测 BFF | backend/services/factor/re_backtest_bff.py、re_backtest_jobs.py | 适配异步任务、轮询和产品展示 |
| 因子目录适配 | backend/services/factor/re_factor_catalog.py | 通过 HTTP 拉取官方目录并缓存到 PostgreSQL |
| 行情适配 | backend/services/data/market_data_bff.py | 通过 HTTP 获取展示行情，不读取本地 marketdata |
| 策略服务 | backend/services/strategy/ | 保存配置、读取兼容策略快照、调用回测接口 |
| 产品缓存 | backend/services/factor/dashboard_store.py 等 | 保存可再生展示缓存，不拥有回测事实 |

## 3. 因子回测时序

因子回测通常是异步交互，具体路径和字段由 ResearchEngine API 契约定义：

~~~text
前端提交因子/日期/资产快照
        ↓
SVQuant backend 鉴权并校验请求
        ↓
POST ResearchEngine 因子回测接口
        ↓
返回 run_id/task_id
        ↓
SVQuant backend 轮询 ResearchEngine 状态接口
        ↓
读取结果或错误
        ↓
保存可再生的产品展示缓存并返回前端
~~~

SVQuant 传递用户已确认的证券池、基准、日期、参数和因子引用；ResearchEngine 负责验证其
是否能在当前数据 release 上执行。SVQuant 不读取结果 SQLite，也不根据本地文件推断任务状态。

## 4. 策略回测时序

~~~text
策略编辑器/策略广场
        ↓
SVQuant 保存策略配置和权限信息
        ↓
请求通过 backend strategy service
        ↓
ResearchEngine HTTP 策略回测接口
        ↓
SVQuant 解析结果、显示净值/指标/持仓
~~~

内置策略目录由 ResearchEngine 管理，SVQuant 通过 `GET /api/strategies` 同步元数据到
`builtin_strategies` 表。页面只展示元数据并提交 `strategy_id`；内置策略源码由
ResearchEngine 校验和执行，SVQuant 不保存或执行本地内置策略源码。

## 5. 两类执行模式

ResearchEngine 当前对外可能提供因子回测和策略回测两类 API；策略内部的向量化/事件模式、
任务管理、撮合规则和结果模型属于 ResearchEngine 内部实现。

SVQuant 只依赖以下稳定事实：

- 请求必须经过 ResearchEngine 的公开 API 契约校验。
- 计算结果必须带有可追溯的任务或运行标识、数据版本和错误信息。
- 异步接口需要通过状态接口确认终态，不能把“已提交”当成“已完成”。
- 失败、取消、超时和服务不可达都必须向用户返回明确状态。

若 ResearchEngine 扩展执行模式，优先新增或版本化 HTTP 字段，不在 SVQuant 复制执行逻辑。

## 6. 配置、网络和安全

- ResearchEngine 地址唯一来源是 backend/.env 的 YG_RE_BASE。
- 前端开发代理读取同一份 backend/.env；业务 TS 文件不保存地址。
- ResearchEngine 凭据、数据库密码和 LLM 密钥只存在本地 .env 或部署密钥系统中。
- 浏览器只携带 SVQuant 的会话凭据；ResearchEngine 地址和内部凭据不暴露给浏览器。
- 网关必须限制允许转发的路径和方法，避免把任意内网 URL 变成代理能力。

## 7. 测试和发布

ResearchEngine 独立仓库维护：

- API schema、响应示例和契约测试；
- 因子、策略、行情和回测结果的计算测试；
- 数据 manifest/质量报告校验；
- 服务自身的启动、健康检查和结果存储测试。

SVQuant 维护：

- 网关参数转换、认证和错误映射测试；
- 前端请求/展示测试；
- 与指定 ResearchEngine 版本配套的集成验证；
- 发布配置和人工回滚记录。

两个仓库必须锁步发布。任何接口字段变化，都应先更新 ResearchEngine 契约测试，再同步
SVQuant BFF、前端类型/文案和集成验证。
