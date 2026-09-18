# SVQuant 系统架构设计

> 本文档描述 SVQuant 产品层的当前架构，以及它与独立 ResearchEngine 的跨仓库边界。
> ResearchEngine 内部实现、API 契约和契约测试以独立仓库为准：
> https://gitee.com/yanggu-yuanqi-intelligence/research-engine

## 1. 系统定位

SVQuant 面向量化投研产品体验，承载用户、权限、社区、知识库、因子/策略配置和结果展示。
ResearchEngine 面向研究计算，承载行情读取、因子计算、策略执行、回测编排和回测结果管理。
拆分后的两个项目不共享 Python 运行时包，也不共享数据库连接。

~~~text
SVQuant/
├── frontend/                 # 产品主前端
├── backend/                  # 产品 API、鉴权、BFF 和业务持久化
│   ├── app/                  # FastAPI 入口和路由
│   ├── services/             # 用户、社区、资讯、数据/因子/策略 BFF
│   ├── ai/                   # 产品侧 AI 编排和供应商适配
│   ├── factor/               # 自定义因子同步产物和接口说明
│   └── requirements.txt
├── KnowledgeHub/             # 知识库产品模块
├── Strategy/                 # 暂存的策略库兼容快照
└── docs/                     # SVQuant 与跨仓库文档
~~~

独立部署的 ResearchEngine 不属于本仓库目录树。它通过 HTTP 暴露研究 API，并在自己的部署
环境中配置和管理行情目录、因子/策略运行时资源以及回测结果 SQLite。

## 2. 责任边界

| 领域 | SVQuant | ResearchEngine |
|------|---------|----------------|
| 用户、登录、JWT、权限 | 负责 | 不负责 |
| 用户资产、因子/策略配置 | 负责保存、鉴权、展示 | 接收已解析的请求快照，不拥有 CRUD |
| 社区、资讯、知识库 | 负责 | 不负责 |
| 行情目录和数据版本校验 | 不保存、不读取 | 负责读取部署环境中的已发布数据 |
| 因子目录、因子计算 | 保存用户自定义同步状态；通过 API 展示/调用 | 负责官方因子目录、校验和计算 |
| 策略执行和回测 | 保存配置、展示结果、调用网关 | 负责执行、撮合语义和结果生成 |
| 回测结果 SQLite | 不直接访问 | 负责存储和查询 |
| API 契约及契约测试 | 使用并做网关集成验证 | 维护权威契约和契约测试 |
| Web 页面 | 负责 | 不负责 |

Strategy/libraries 是当前仍被 SVQuant 后端读取的兼容快照，暂时保留。它不表示 SVQuant
拥有策略执行引擎；执行仍通过 ResearchEngine API 完成。根目录 Factor/ 已移除，不再作为
SVQuant 的代码、数据或缓存目录。

## 3. 请求拓扑

~~~text
用户浏览器
    │ 只访问 SVQuant frontend / backend
    ▼
SVQuant backend
    ├─ 鉴权、权限和参数校验
    ├─ 用户资产解析与请求快照
    ├─ ResearchEngine 网关（HTTP）
    ├─ 错误码/超时映射
    └─ PostgreSQL、产品缓存和展示适配
             │
             │ YG_RE_BASE
             ▼
ResearchEngine
    ├─ marketdata（外部已发布数据）
    ├─ 因子/策略计算
    ├─ 回测任务与结果
    └─ 回测结果 SQLite（服务部署侧）
~~~

前端主应用通过 /api 访问 SVQuant backend；前端不得把 ResearchEngine 地址写入业务代码。
ResearchEngine 地址只在 backend/.env 的 YG_RE_BASE 中配置。Vite 开发代理也读取同一份
配置，避免前后端出现两个不一致的地址来源。

## 4. SVQuant 模块职责

### 4.1 frontend

- 登录、用户操作、因子/策略配置、社区、知识库和结果展示。
- 所有需要研究计算的操作调用 SVQuant backend。
- 不直接访问 ResearchEngine，不保存研究服务凭据。

### 4.2 backend/app

- FastAPI 入口、路由、鉴权依赖和统一错误处理。
- 将用户请求转换为网关可接受的 API 请求。
- 不在路由层实现行情读取、因子计算或策略回测。

### 4.3 backend/services

- auth、community、news、core：平台业务、数据库和通用基础设施。
- data：通过 ResearchEngine API 获取行情并做产品侧字段适配、缓存和展示。
- factor：管理用户自定义因子同步状态、官方目录缓存、检测/回测请求和展示指标。
- strategy：管理策略配置、策略库兼容快照、权限和结果展示；不执行回测。
- re_* 和 re_gateway：ResearchEngine 的 HTTP BFF/网关，不复制其计算逻辑。

backend/output/ 中的 SQLite 或 JSON 是可再生的产品缓存，不是 ResearchEngine 的结果库，也
不是跨服务审计事实。用户、权限、配置和审计事实写入 SVQuant PostgreSQL。

### 4.4 KnowledgeHub

知识库的 API、页面、文档元数据和附件管理属于 SVQuant 产品层。附件文件按本项目的
KnowledgeHub/data/ 规则管理；ResearchEngine 不依赖它。

## 5. 外部资源和部署边界

| 资源 | 位置/入口 | 归属 |
|------|-----------|------|
| PostgreSQL | backend/.env 的 DATABASE_URL | SVQuant |
| ResearchEngine | backend/.env 的 YG_RE_BASE | 独立 ResearchEngine 部署 |
| marketdata | SVQuant 外部的 project/marketdata 或 ResearchEngine 配置目录 | ResearchEngine 与数据发布方 |
| 回测结果 SQLite | ResearchEngine 配置的结果存储目录 | ResearchEngine |
| LLM、资讯源 | SVQuant backend 配置 | SVQuant |
| Strategy/libraries | SVQuant 仓库内的兼容快照 | SVQuant 暂存，后续再治理 |

marketdata 中的 data_manifest.yaml 和 quality_report.json 属于外部数据发布物，不应被复制回
SVQuant 或提交到本仓库。ResearchEngine 在启动/运行时按自己的配置读取并校验版本或哈希。

## 6. API 和版本约束

- ResearchEngine 的公开 API、响应字段、兼容窗口和契约测试由独立仓库维护。
- SVQuant backend 只依赖公开 HTTP 契约，不依赖 ResearchEngine 内部模块路径或文件布局。
- SVQuant 网关负责认证、用户资产快照、超时、连接失败和 ResearchEngine 错误到产品错误的映射。
- ResearchEngine 与 SVQuant 必须锁步发布：先确认 API 契约和契约测试，再同时更新网关、页面、
  运行配置和发布记录。
- 任一服务不可用时，SVQuant 应明确显示“研究服务暂不可用”，不能伪造计算结果或回退到本地
  隐式计算。

## 7. 配置和启动

SVQuant 只提供产品层启动方式：

~~~bash
cp backend/.env.example backend/.env
# 手工填写 DATABASE_URL、JWT_SECRET、YG_RE_BASE 等配置
conda activate svquant
cd backend
pip install -r requirements.txt
python -u api_server.py
~~~

ResearchEngine 的安装、数据校验、结果库和服务启动由其独立仓库负责。本仓库不再提供
ResearchEngine 的安装脚本、启动脚本或内部配置。

## 8. 失败与回滚

| 故障 | SVQuant 行为 | 处理责任 |
|------|--------------|----------|
| ResearchEngine 连接失败/超时 | 网关返回明确的服务不可用错误，前端保留用户输入 | ResearchEngine 运维和网络配置 |
| API 响应不兼容 | 集成测试或网关校验阻断发布 | 两仓库共同修复并锁步发布 |
| marketdata 版本/哈希不匹配 | ResearchEngine 拒绝计算；SVQuant 展示计算服务不可用 | 数据发布方和 ResearchEngine |
| PostgreSQL 不可用 | SVQuant 登录和产品写操作失败 | SVQuant 运维 |
| 产品缓存损坏 | 删除后按 ResearchEngine API 重建 | SVQuant |
| 版本发布异常 | 按人工回滚方案恢复上一组兼容版本 | 发布负责人 |

## 9. 后续演进

本轮不设计共享领域库、分布式任务队列、统一对象存储、实盘执行或自动回滚。若未来需要，
先更新跨仓库契约和 ADR，再分别修改两个项目，避免通过复制代码重新形成耦合。
