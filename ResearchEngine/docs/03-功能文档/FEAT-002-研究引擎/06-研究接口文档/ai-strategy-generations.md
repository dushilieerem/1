# AI 向量化策略草稿生成 API

> 状态：受控 MVP，开发中。关联：[FEAT-019](../../FEAT-019-AI向量化策略生成API/README.md)。

## 1. 概述

`POST /api/ai/strategy-generations` 将研究员的自然语言假设转换为一个可审阅的日频自由向量化策略草稿。服务端调用已配置的火山方舟模型，并在返回前校验模型输出 JSON、Python AST 与源码编译语法。

端点只生成代码，**不会执行代码、不会自动回测、不会产生订单或交易指令**。前端必须展示草稿及风险提示；用户确认后，才可将 `strategy_code` 提交给[策略回测 API](backtest-strategy.md)。

```text
自然语言 → 火山方舟生成 → JSON 解析 → AST/编译校验 → 策略草稿
                                                        ↓ 用户确认
                                           POST /api/backtest/strategy
```

## 2. 请求

### `POST /api/ai/strategy-generations`

请求体必须是 JSON，未知字段返回 `422`。

```json
{
  "prompt": "生成一个每 20 日调仓、买入过去 20 日动量最高 30 只股票的等权策略。",
  "context": {
    "universe": "CSI500",
    "frequency": "1d",
    "preferred_strategy_name": "MomentumTop30Strategy"
  },
  "idempotency_key": "8ecb2eb2-6f7f-4d64-93b2-7e63b34ff2a8"
}
```

| 字段 | 类型 | 必填 | 默认值 | 规则与用途 |
|---|---|:---:|---|---|
| `prompt` | string | 是 | — | 1–2,000 个字符。描述研究假设、选股逻辑和预期调仓方式；不得放入 API Key、账户信息或未公开数据。服务端将其作为不可信输入传给受控提示词。 |
| `context` | object | 否 | `{}` | 非敏感研究上下文，只影响模型生成提示，不改变数据权限、回测参数或实际股票池。 |
| `context.universe` | string/null | 否 | `null` | 希望研究的股票池，例如 `CSI500`。仅用于告知模型和帮助前端预填后续回测请求；生成服务不验证或解析该股票池。 |
| `context.frequency` | string | 否 | `1d` | 当前仅支持日频 `1d`；其他值由 Pydantic 拒绝并返回 `422`。 |
| `context.preferred_strategy_name` | string/null | 否 | `null` | 希望模型使用的 Python 策略类名。最终仍以模型返回且通过校验的 `strategy_name` 为准；不保证一定采用此名称。 |
| `idempotency_key` | UUID string | 是 | — | 本 Python 服务进程内的幂等键。相同键且请求内容相同会返回第一次结果；相同键但请求内容不同返回 `409`。进程重启后失效。 |

## 3. 成功响应

仅当 `status` 为 `ready` 时，`strategy` 一定存在，且 `validation.status` 为 `passed`。

```json
{
  "generation_id": "sg_7b76aa3cc2b54d8995ca080fce01f2db",
  "status": "ready",
  "strategy": {
    "strategy_name": "MomentumTop30Strategy",
    "strategy_code": "import pandas as pd\\n\\nclass MomentumTop30Strategy:\\n    def __init__(self, close):\\n        self.close = close\\n\\n    def generate_signals(self):\\n        momentum = self.close.pct_change(20)\\n        ranks = momentum.rank(axis=1, ascending=False, method='first')\\n        weights = pd.DataFrame(0.0, index=self.close.index, columns=self.close.columns)\\n        weights[ranks <= 30] = 1.0 / 30\\n        return weights",
    "description": "持有过去 20 日价格动量最高的 30 只股票并等权配置。",
    "used_fields": ["close"],
    "assumptions": ["close 是按日期和标的对齐的日频面板。"],
    "warnings": ["该草稿未经回测验证，不构成投资建议。"]
  },
  "validation": {
    "status": "passed",
    "capability_catalog_version": "2026-07-30",
    "errors": [],
    "warnings": []
  },
  "meta": {
    "model_alias": "ark-code-latest",
    "prompt_version": "v1",
    "latency_ms": 2468
  }
}
```

| 响应字段 | 类型 | 说明 |
|---|---|---|
| `generation_id` | string | 本次生成的服务端唯一标识，格式为 `sg_` 加随机值。当前仅供前端展示、日志关联和问题定位，不是可持久化策略资产 ID。 |
| `status` | `ready` / `rejected` | `ready` 表示模型输出已通过当前静态校验；`rejected` 表示输出无法解析或不符合受控策略契约。它不表示策略收益、可交易性或经济有效性。 |
| `strategy` | object/null | 可回顾的策略草稿。仅 `ready` 时存在；`rejected` 时固定为 `null`。 |
| `strategy.strategy_name` | string | 策略类名，必须与 `strategy_code` 内唯一策略类的名称完全一致。前端提交回测时不单独传该字段。 |
| `strategy.strategy_code` | string | 完整 Python 源码。仅允许 `import pandas as pd` 和唯一一个策略类；类必须只定义 `__init__(self, close)` 与 `generate_signals(self)`。后者必须返回“日期 × 标的”目标权重 `pandas.DataFrame`。 |
| `strategy.description` | string | 模型生成的策略逻辑说明，仅用于展示，不参与校验或回测。 |
| `strategy.used_fields` | string[] | 模型声明使用的数据字段。当前白名单只有 `close`；声明未知字段会被拒绝。该列表供前端解释使用，不能替代源码审核。 |
| `strategy.assumptions` | string[] | 模型列出的数据、逻辑或适用范围假设。可能为空数组。 |
| `strategy.warnings` | string[] | 模型生成的风险提示。可能为空数组；前端仍必须固定展示“未经回测验证、不构成投资建议”的平台提示。 |
| `validation` | object | 服务端 JSON、AST 和编译校验的结构化结果，所有响应均存在。 |
| `validation.status` | `passed` / `failed` | 当前草稿的静态校验状态。只有 `passed` 对应 `ready`。 |
| `validation.capability_catalog_version` | string | 本次校验使用的字段和语法能力目录版本，用于前端展示与问题追踪。 |
| `validation.errors` | string[] | 校验失败的简短原因。`passed` 时为空数组；不得把供应商原始异常或密钥展示给用户。 |
| `validation.warnings` | string[] | 服务端校验产生的非阻塞警告；当前 MVP 通常为空数组。 |
| `meta` | object | 本次生成的非敏感运行元数据，所有响应均存在。 |
| `meta.model_alias` | string | 实际使用的服务端模型别名，不包含 API Key 或供应商鉴权信息。 |
| `meta.prompt_version` | string | 服务端受控提示词模板版本，便于追溯生成条件。 |
| `meta.latency_ms` | integer | 从供应商调用开始到本地校验完成的耗时，单位为毫秒。 |

### 策略源码与权重语义

`generate_signals()` 返回的 DataFrame 索引为交易日、列为标的代码。正数表示多头目标权重，`0.0` 表示明确清仓，`NaN` 表示不更新、沿用上一期目标。MVP 生成端点只允许访问 `self.close`，不支持事件驱动订单、持仓状态或其他行情/基本面字段。

## 4. 已拒绝的草稿

供应商成功返回内容、但输出不符合受控策略契约时，HTTP 仍为 `200`，响应为 `rejected`。前端不得提供回测按钮；应展示 `validation.errors` 的简短原因并允许用户修改自然语言后重新生成。

```json
{
  "generation_id": "sg_31d9...",
  "status": "rejected",
  "strategy": null,
  "validation": {
    "status": "failed",
    "capability_catalog_version": "2026-07-30",
    "errors": ["只允许 import pandas as pd"],
    "warnings": []
  },
  "meta": {
    "model_alias": "ark-code-latest",
    "prompt_version": "v1",
    "latency_ms": 1810
  }
}
```

## 5. 前端接入流程

1. 用户填写策略研究假设；客户端生成一个新的 UUID 作为 `idempotency_key`。
2. 调用本端点，并始终根据 `status` 渲染结果。
3. `ready` 时展示代码、说明、字段、假设和警告，并允许复制或编辑。
4. 用户确认且未修改代码时，调用策略回测：

```json
{
  "strategy_code": "<strategy.strategy_code>",
  "universe": "CSI500",
  "benchmark": "CSI300",
  "include_positions": true
}
```

5. 用户编辑代码后，必须清除“已通过 AI 校验”标识。当前 MVP 没有独立的策略重新校验端点，不能将编辑后的代码视为经过本端点校验。

## 6. HTTP 状态与重试

| HTTP 状态 | 场景 | 客户端处理 |
|---:|---|---|
| `200` | 已生成草稿；查看响应中的 `ready` / `rejected`。 | `ready` 可进入用户确认；`rejected` 提示修改自然语言后重试。 |
| `409` | 同一 `idempotency_key` 对应不同请求内容。 | 生成新的 UUID 后重新提交。 |
| `422` | 请求字段、UUID、长度、频率或未知字段不符合 Pydantic 契约。 | 修正请求后再提交，不自动重试。 |
| `503` | 未配置密钥，或供应商不可用、鉴权失败、模型不可用等非超时错误。 | 显示“AI 服务暂不可用”；稍后重试并由运维检查服务端配置。 |
| `504` | 供应商调用超过 20 秒。 | 使用新的幂等键重试。 |

当前没有实现应用级 `401`、`403`、`429`；待 SaaS 网关接入鉴权、权限和额度后补充。

## 7. 服务端配置

所有配置仅由部署环境或密钥管理服务注入；浏览器请求不得包含 Key、模型名或 Base URL。

| 环境变量 | 必填 | 默认值 / 用途 |
|---|:---:|---|
| `AI_STRATEGY_API_KEY` | 二选一 | 策略生成服务专用 API Key，优先级最高。 |
| `AI_FACTOR_API_KEY` / `ARK_API_KEY` | 二选一 | 未配置策略专用 Key 时复用现有 AI 因子服务的 Key。 |
| `AI_STRATEGY_BASE_URL` | 否 | 策略服务 Base URL；未设置时回退到 `AI_FACTOR_BASE_URL`，再回退到火山方舟默认地址。 |
| `AI_STRATEGY_MODEL_ALIAS` | 否 | 策略服务模型别名；未设置时回退到 `AI_FACTOR_MODEL_ALIAS`，再回退到 `ark-code-latest`。 |

调用优先请求 `response_format.json_schema`。若模型明确不支持该参数，服务降级为受控提示词 JSON 输出，但始终保留本地 JSON、AST 和编译校验。

## 8. 限制与后续工作

- 幂等记录只保存在单个 Python 进程内，进程重启或多实例部署后不共享。
- 没有用户身份、租户隔离、调用配额、成本计量或持久化审计。
- 当前白名单只允许日频 `close` 面板与自由目标权重策略；不支持结构化因子组合策略或事件驱动策略。
- 生成服务不执行代码；生产回测必须部署为无网络、只读数据、CPU/内存/时限受控的子进程或容器。
- 静态校验不能保证无未来函数、市场可交易性或收益能力；平台不提供投资建议或收益承诺。
