# Technical Design：AI 自然语言因子生成 API

## 架构边界

新增 `AI Research Service`（可先作为 SaaS 应用层中的独立模块），承担身份、额度、提示词、供应商调用、静态校验和审计。`ResearchEngine` 继续是纯计算服务，只接收确认后的 `factor_code` 进行回测；`QuantCore` 不引入 LLM SDK 或供应商依赖。

```text
Web App
  │  POST /api/ai/factor-generations（JWT、幂等键）
  ▼
AI Research Service
  ├─ Auth / quota / idempotency / audit
  ├─ CapabilityCatalog（字段、方法、AST 白名单）
  ├─ PromptBuilder + structured-output schema
  ├─ LLMProvider（第三方适配器；服务端密钥）
  └─ FactorCodeValidator（JSON + AST + compile）
  │
  └─ 返回可审阅因子草稿
             │ 用户确认
             ▼
       ResearchEngine POST /api/backtest/factor
             ▼
            QuantCore
```

## 模块与接口

| 模块 | 职责 | 不负责 |
|---|---|---|
| `ai_factor_api.routes` | HTTP 契约、认证上下文与错误映射 | 直接运行回测或拼接 Python |
| `generation_service` | 幂等、额度、生成流程编排和审计 | 供应商 SDK 细节 |
| `providers.base.LLMProvider` | `generate_factor(request, schema) -> ProviderResult` 抽象 | 业务校验、用户权限 |
| `providers.<vendor>` | 第三方认证、超时、重试和结构化输出调用 | 返回未校验代码给 Web |
| `capability_catalog` | 发布可用字段、内置库方法、签名、版本和弃用信息 | 从运行时任意 Python 对象自动暴露 API |
| `factor_code_validator` | JSON Schema、AST 白名单、签名、字段/方法和 compile 校验 | 判断因子经济有效性 |
| `generation_repository` | 幂等映射、配额计数和脱敏审计记录 | 因子资产管理或回测结果存储 |

当前受控 MVP 已在 `researchengine.api.ai_factor` 实现路由、火山方舟 OpenAI 兼容调用、内存幂等、结构化解析和 AST 校验；应用层身份、跨实例持久化幂等/审计与套餐额度待 SaaS 基础设施具备后迁移实现。该过渡实现不会执行或自动回测模型输出。

### Provider 抽象

```python
class LLMProvider(Protocol):
    def generate_factor(
        self, *, messages: list[dict[str, str]], response_schema: dict, timeout_seconds: int
    ) -> ProviderResult: ...
```

部署通过 `AI_FACTOR_PROVIDER` 和 `AI_FACTOR_MODEL_ALIAS` 选择适配器；真实供应商模型名、Base URL 和 Key 只存在服务端密钥配置。首期固定使用字节火山方舟 AgentPlan API，默认模型为 `ark-code-latest`，Base URL 为 `https://ark.cn-beijing.volces.com/api/plan/v3`。接口抽象仅用于避免调用点与供应商耦合，不提前实现多供应商路由。

部署配置只允许由服务端注入；严禁将真实 Key 写入代码、文档、前端构建变量或测试固件：

| 配置项 | 值 / 来源 |
|---|---|
| `AI_FACTOR_PROVIDER` | `volcengine_ark` |
| `AI_FACTOR_BASE_URL` | `https://ark.cn-beijing.volces.com/api/plan/v3` |
| `AI_FACTOR_MODEL_ALIAS` | `ark-code-latest`（可由部署配置覆盖） |
| `AI_FACTOR_API_KEY` / `ARK_API_KEY` | 密钥管理服务或部署环境变量；兼容火山方舟 SDK 的 `ARK_API_KEY`，不入库、不写入日志 |

## 生成与校验流程

1. 校验认证、额度、`prompt`、频率、请求上下文和幂等键；同键命中直接返回保存结果。
2. 载入固定版本的能力目录。目录只包含当前 `FactorLibrary` 可访问的字段、允许 `pandas` 运算和明确批准的内置方法。
3. 系统提示词要求仅按 JSON Schema 输出，并声明：不得臆造字段、不得使用未来数据、不得输出投资建议；用户 prompt 作为不可信文本，不得覆盖系统约束。
4. Provider 优先使用火山方舟 `response_format.json_schema` 严格模式；模型明确不支持时，自动降级为受控提示词 JSON 输出，再由本地 JSON Schema 和 AST 校验。解析失败产生 `rejected`。
5. 验证 AST：模块仅有一个 `FunctionDef`；第一个参数为 `self`；节点、名称、属性访问和调用必须位于白名单；拒绝 import、赋值到全局、异常类构造、双下划线访问、动态调用和可疑字面量。
6. 将代码交给与 ResearchEngine 相同版本的 `_wrap_factor_code` 规则进行 `compile`，只验证而不 `exec`。通过后记录 `ready`；否则记录 `rejected`。
7. 返回代码与可解释元数据。只有用户显式确认并通过回测 API 的执行隔离，代码才会被运行。

## 数据与审计

MVP 使用应用层关系数据库或现有平台存储实现如下逻辑实体；不新增 ResearchEngine 数据表。

| 实体 | 关键字段 | 保留策略 |
|---|---|---|
| `factor_generation` | `generation_id`、tenant/user、请求/输出哈希、状态、模型别名、模板/目录版本、用量、耗时、错误码、创建时间 | 审计元数据至少 90 天 |
| `idempotency_record` | tenant、幂等键、请求哈希、`generation_id`、过期时间 | 24 小时 |
| `quota_usage` | tenant、时间窗、请求数、输入/输出 token、成本估算 | 按计费与财务策略 |
| `capability_catalog_version` | 版本、内容哈希、状态、发布时间 | 与关联生成记录共同保留 |

原始 prompt 与原始模型响应属于可配置的短期调试数据，默认 30 天删除；审计采用哈希和最小化元数据。禁止持久化密钥、Authorization 头、完整供应商请求体和未脱敏敏感字段。

## 安全、兼容与回滚

- 本 Feature 不扩大既有 ResearchEngine 对任意 Python 的执行信任边界。生产上线前，确认后的回测请求仍必须部署在受限子进程/容器中：只读数据挂载、无出网、CPU/内存/时限和非特权用户。该部署项是 AI API 上线的前置条件。
- AST 校验采用默认拒绝策略，允许集合由单元测试覆盖；任何新增字段或函数都必须先更新能力目录和测试，不能仅更新提示词。
- Provider 请求使用连接/总超时、有限指数退避和熔断；不可重试的 4xx 不重试，带幂等键的网络失败可安全重试。首期适配器仅面向已选定的火山方舟 Base URL 和模型别名实现；不得允许客户端覆盖它们。
- 回滚时通过功能开关关闭 `/api/ai/factor-generations` 或把其设为只返回 `503`；既有 `/api/backtest/factor`、内置因子库和手写因子路径不受影响。关闭后停止新的供应商调用，保留审计记录。

## 测试策略

- 单元：请求校验、配额、幂等、提示词组装、Provider 错误映射、JSON Schema、AST 正负样例、能力目录版本化。
- 合约：使用假 Provider 固定返回，验证响应可直接映射为 `FactorBacktestRequest`；不在测试中调用真实 LLM。
- 集成：在隔离的 ResearchEngine 测试数据上，将已验证的生成函数提交因子回测，验证现有 API 契约保持不变。
- 安全：覆盖 import、`open`、socket、requests、`__class__`、`getattr`、`eval`、循环资源消耗和提示词注入文本；前者必须拒绝，后者不得改变系统约束。
- 上线前：使用脱敏的人工标注提示集评估字段正确率、可编译率、校验拒绝率、回测可运行率与平均成本；仅在指标达标后灰度开启。

## 关键风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| LLM 幻觉字段或未来函数 | 代码不可运行或研究失真 | 版本化能力目录、结构化输出、AST 与字段校验、回测前用户审阅 |
| 生成代码逃逸 | 主机、数据和凭据风险 | 默认拒绝 AST、禁止自动执行、生产回测子进程/容器隔离 |
| 密钥、用户数据或提示词泄露 | 合规与安全风险 | 服务端密钥管理、最小化上下文、日志脱敏、供应商数据协议评审 |
| 供应商不可用或成本失控 | 用户体验和毛利风险 | 限流/额度、超时熔断、幂等、单供应商降级提示与用量审计 |
| 回测成功被误读为有效策略 | 产品与合规风险 | 明确研究草稿标签、强制展示警告与成本/回撤、禁止自动交易 |
