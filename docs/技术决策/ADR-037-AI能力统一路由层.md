# ADR-037：AI 能力统一路由层

- 日期：2026-10-30
- 状态：已采纳；P0（路由层骨架 + 调用点收敛）与 P1-1（读帖摘要）、P1-2（回测解读）已落地，其余能力按 §7 分批迁入
- 关联：[INIT-003 AI 平台](../产品与需求/倡议/INIT-003-AI平台/domain-design.md)、[ADR-029 研究服务采用 services 与 models 分层](ADR-029-研究服务采用services与models分层.md)

## 问题

AI 能力在 SVQuant 与 ResearchEngine（下称 RE）两侧各自生长，已经出现四类重复与三个硬编码分支：

1. **同一件事三份实现**：`backend/ai/gateway/llm_client.py`（`LLM_*`，支持 function calling）、
   `backend/ai/gateway/ark_chat.py`（`ARK_API_KEY`/`AI_FACTOR_*`/`SILICONFLOW_*`，支持 SSE）、
   RE 的 `app/api/llm_provider.py`（`AI_*`，带 `response_format` 降级重试）。三份的异常类型、超时口径、
   token 统计字段都不一致。
2. **模型与参数散落在每个调用点**：现有 11 处 `chat_completions` 调用各自写 `temperature`/`max_tokens`，
   换模型要逐个改；RE 侧更按能力拆出 `AI_STRATEGY_*`、`AI_TRANSCRIPTION_*` 等多个前缀，命名空间膨胀到四套。
3. **“这个功能走谁”是代码分支而非配置**：`app/routers/re_gateway.py` 把 4 个 AI 端点整段转发给 RE；
   `services/community/ai_summary.py` 先判 `YG_RE_BASE` 再决定是否调 RE；
   `ai/runtime/skills.py` 里先判 `llm_configured()` 再回退 mock。三者互不知情，新增能力只能再叠一个 `if`。
4. **错误语义靠字符串匹配**：`app/routers/ai.py` 用 `"未配置" in msg` 反推 HTTP 503，还带着
   `"鏈" in msg and "厤" in msg` 的乱码兜底；同文件已沉淀出 `缂哄皯 audio_base64`、`鏃犳晥` 这类
   GBK→UTF-8 坏字面量。上游一改文案，状态码就错。
5. **没有统一落点**：新增一个 AI 功能，要同时动 router、`.env`、前端，必要时还要在 RE 加端点。

结论：需要一层，让“业务要什么”和“由谁、用哪个模型、失败怎么办”分开。

## 选择

### 1. 分两层：L1 供应商层 + L2 任务路由层

```
业务代码（app/routers、ai/runtime、ai/crews）
        │  run(task, variables) / stream(task, messages)
        ▼
L2  ai/router/     任务路由层：TaskSpec 注册表、执行链、校验、配额、统计、异常归一
        ▼
L1  ai/gateway/    供应商层：provider 解析、HTTP、SSE、重试、response_format 降级、token 统计
        ▼
    火山方舟 / 硅基流动 / OpenAI 兼容 / 研究计算服务（RE）
```

两条硬规则，作为 code review 的检查项：

- **L2 之上不出现供应商名**：业务代码里不得出现 `ark`、`siliconflow`、`RE`、`base_url`、`api_key`。
- **L1 之下不出现业务词**：`ai/gateway/` 不认识“因子生成”“社区摘要”，只认识 messages 和 token。

### 2. TaskSpec 是唯一扩展点

新增 AI 能力 = 注册一个 TaskSpec + 写一个 prompt/校验模块，不改路由层本身。

| 字段 | 作用 |
|---|---|
| `task_id` | 稳定标识，如 `community.polish_title`；也是日志、用量、缓存的键 |
| `slot` | 模型档位（`default` / `code` / `fast`），不是具体模型名 |
| `temperature` / `max_tokens` | 任务级参数，替代调用点硬编码 |
| `timeout_sec` | 任务级超时（转写类需远大于默认值） |
| `response_format` | JSON Schema；供应商不支持时由 L1 降级重试一次 |
| `validator` | 输出校验器（AST 白名单、字段闭集、JSON 结构） |
| `executors` | 执行链，见下条 |
| `mock` | 无 Key 时的确定性兜底（仅供联调，产物必须标注 `mock_local`） |
| `quota_cost` | 预估消耗，供 `ai/runtime/store` 预扣/记账 |
| `idempotency` | 是否按请求哈希去重（转写、解读需要） |
| `stream_capable` | 是否提供流式入口 |

### 3. 执行链是配置，不是分支

`executors = ("local", "re", "mock")` 按序尝试，前一个抛 `NotConfigured` 才降级到下一个，
抛 `UpstreamUnavailable` / `BadOutput` 则直接上抛（不静默换执行者）。
“走 RE 还是走本地”由部署配置决定（有无 `YG_RE_BASE`、`AI_EXECUTOR_ORDER`），代码里不写 `if`。
P2 完成后 RE 分支默认关闭，仅保留为灰度回退手段。

### 4. 类型化异常，边界统一映射

| 异常 | 语义 | HTTP |
|---|---|---|
| `AiNotConfigured` | 缺 Key / 缺 base_url | 503 |
| `AiUpstreamError` | 上游 HTTP/网络/超时 | 502（超时 504） |
| `AiBadOutput` | 返回内容不满足契约 | 502 |
| `AiQuotaExceeded` | 配额不足 | 429 |
| `AiInvalidRequest` | 输入校验失败 | 422 |

路由层只抛这五种；`app/routers/*` 里禁止再按字符串猜状态码。既有 `LlmError` / `ArkChatError` /
`SpeechError` 继承 `AiError` 保留兼容，新代码一律抛新类型。

### 5. 配置收敛

- 保留 `LLM_*`、`ARK_API_KEY`、`AI_FACTOR_*`、`SILICONFLOW_*` 作为**读取别名**，不破坏现有 `.env`。
- 新增唯一写入口：`AI_SLOT_DEFAULT` / `AI_SLOT_CODE` / `AI_SLOT_FAST` 指定档位到模型；
  `AI_<TASK>_MODEL` 作为任务级覆盖（可选）。
- RE 的 `AI_STRATEGY_*`、`AI_TRANSCRIPTION_*` 不再新增；迁移完成后由 `AI_SLOT_*` 承担。

### 6. 必须保留的既有能力（不得为了“统一”去掉）

- 配额与记账：`ai/runtime/store.assert_quota_available` / `record_usage`，接入点在路由层执行前/后。
- SSE 流式：SV 助手 `iter_chat_stream` 与 `/api/ai/chat?stream` 的帧格式不变。
- function calling：`tools` / `tool_choice` 透传，`strategy_research` 依赖多轮工具调用。
- 长任务：转写类单次 600s，路由层支持 `defer` 模式（202 + 轮询），不占同步连接。
- mock 兜底：无 Key 联调可用，但产物必须标注 `mock_local`，不得伪装成 AI 结果。

### 7. RE 五个 AI 能力的迁移口径

迁移的是 **prompt + 校验器 + 响应契约**，不是 transport。RE 的 `llm_provider` 不复制进 SVQuant。

| 能力 | RE 源文件 | task_id | 迁移难点 | 批次 |
|---|---|---|---|---|
| 读帖摘要 | `ai_post_summary.py` | `community.summarize_post` | 已在本仓有本地路径，只需接管 RE 分支 | P1-1 |
| 回测解读 | `ai_interpretation.py` | `research.interpret_backtest` | evidence package 结构需前端契约对齐 | P1-2 |
| 因子生成 | `ai_factor.py` | `research.generate_factor` | 依赖 RE `_wrap_factor_code` 的因子外壳合同 | P1-3 |
| 策略生成 | `ai_strategy.py` | `research.generate_strategy` | 同上，合同更松 | P1-3 |
| 聚宽转写 | `ai_strategy_transcription.py` | `research.transcribe_strategy` | 1395 行；600s 同步调用改为 defer 模式 | P1-4 |

RE 侧 AI 端点保留一个版本周期做为灰度回退，之后下线（ADR 后续补记）。

## 备选方案

- **把 RE 的 AI 代码整段复制进 SVQuant 再包一层**：会得到第三套 transport，错误语义再分叉一次，不采用。
  复制范围限定为 prompt 与校验器。
- **继续让 RE 当 AI 后端，SVQuant 只做反向代理**：Key 与配额留在两侧，SVQuant 的用户体系与计费无法统一；
  RE 无 `require_user`，多租户隔离无处落地。不采用。
- **只做一个 `gateway.chat()` 把参数全塞给调用方**：解决了 transport 重复，但模型/温度/校验仍散在 11 个调用点，
  无法回答“换模型要改几处”。不采用。
- **直接引入 LiteLLM 等 SDK 作为 L1**：多一层外部依赖与运维面，当前 urllib 实现足够；留作 P3 备选，
  是否替换由 L1 单点决定，不影响 L2。

## 后果

正面：

- 新增 AI 能力只加 TaskSpec + prompt 模块，路由层与 `.env` 不动。
- 超时、重试、降级、token 统计、异常映射只有一份，修一处全仓生效。
- 模型换档从“改 11 处”变成“改 1 个变量”；成本与配额可按 task 归集。
- RE 侧 AI 下线后，SVQuant 可独立部署 AI 能力，不再依赖计算服务的可用性。

代价与约束：

- 一次性重构 11 个调用点，测试需跟随（`test_community_summary_*` 等直接 patch `chat_completions`）。
- 过渡期 `llm_client` / `ark_chat` 保留为 legacy 入口，需要约定：**新代码只准用 `ai.router`**，
  否则会重新长出第四套分支。
- 执行链的降级只在 `AiNotConfigured` 时发生，部署配置错误不会被自动掩盖——这是刻意的，
  静默换执行者会让排查成本高于收益。

## 验证与回滚

- 验证：`backend/tests/` 全量 + 新增 `test_ai_router.py`（档位解析、异常映射、降级只在 NotConfigured 触发、
  stream 与非 stream 分离、validator 生效）；`/api/ai/*` 的 URL、请求体、响应体保持不变，前端不改。
- 回滚：路由层是新增包，`LLM_EXECUTOR` 置为 `legacy` 即恢复直连 `llm_client`/`ark_chat`；
  RE 侧 AI 端点在 P2 完成前不下线，可一键切回转发。
- 不使用 `git reset` 或清空历史数据；回滚按分支回退与配置开关两步走。

## 关联 Feature / ADR

- INIT-003 用户、社区与 AI SaaS 平台：本 ADR 是其 BC1 AI Assistant 的基础设施前提。
- ADR-029：`ai/` 目录沿用 services 与 models 分层的组织方式，不引入额外分层框架。
