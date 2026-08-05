# AI 因子草稿生成 API

> 状态：受控 MVP，开发中。关联：[FEAT-016](../../FEAT-016-ai-factor-generation-api/README.md)。
>
> 本页描述**当前已实现行为**。身份鉴权、调用额度、持久化审计和生产级代码执行隔离尚未接入，见[限制与后续工作](#限制与后续工作)。

## 1. 概述

`POST /api/ai/factor-generations` 将研究员的自然语言假设转换为一个可审阅的 SVQuant 因子函数草稿。服务端调用已配置的火山方舟模型，并在返回前进行 JSON、Python AST 与因子包装编译校验。

端点只生成代码，**不会执行代码、不会自动回测、不会产生交易指令**。前端必须让用户审阅草稿；用户确认后，才可将 `factor_code` 和 `factor_name` 提交到 [因子回测 API](backtest-factor.md)。

```text
自然语言 → 火山方舟生成 → JSON 解析 → AST/编译校验 → 草稿
                                                        ↓ 用户确认
                                             POST /api/backtest/factor
```

## 2. 请求

### `POST /api/ai/factor-generations`

请求体必须是 JSON，未知字段返回 `422`。

```json
{
  "prompt": "生成一个计算过去20个交易日收盘价动量，并使用相对成交量确认的日频因子。",
  "context": {
    "universe": "CSI500",
    "frequency": "1d",
    "allowed_library_names": ["technical_indicators"],
    "preferred_factor_name": "volume_confirmed_momentum_20"
  },
  "idempotency_key": "8ecb2eb2-6f7f-4d64-93b2-7e63b34ff2a8"
}
```

### 字段

| 字段 | 类型 | 必填 | 当前规则 |
|---|---|:---:|---|
| `prompt` | string | 是 | 1–2,000 个字符，描述研究假设。不得包含 API Key、账户信息或未公开数据。 |
| `context` | object | 否 | 缺省为空对象。只用于生成提示词，不改变数据访问权限。 |
| `context.universe` | string/null | 否 | 写入模型上下文和前端后续回测建议；生成服务不解析股票池。 |
| `context.frequency` | string | 否 | 当前只接受 `1d`，默认 `1d`。 |
| `context.allowed_library_names` | string[] | 否 | 当前作为模型上下文传递；MVP 尚不校验库名，也不允许生成函数直接调用 `self.<库方法>()`。 |
| `context.preferred_factor_name` | string/null | 否 | 提示模型优先采用的函数名；最终仍以模型返回并通过校验的 `factor_name` 为准。 |
| `idempotency_key` | UUID string | 是 | 单个服务进程内的幂等键。相同键、相同请求返回第一次结果；相同键、不同请求返回 `409`。进程重启后失效。 |

## 3. 成功响应

当 `status` 为 `ready` 时，`factor` 一定存在且 `validation.status` 为 `passed`。

```json
{
  "generation_id": "fg_7b76aa3cc2b54d8995ca080fce01f2db",
  "status": "ready",
  "factor": {
    "factor_name": "volume_confirmed_momentum_20",
    "factor_code": "def volume_confirmed_momentum_20(self, window=20):\n    momentum = self.close.pct_change(window)\n    volume_ratio = self.volume / self.volume.rolling(window).mean()\n    return momentum * volume_ratio",
    "description": "以20日价格动量结合相对成交量构造因子。",
    "used_fields": ["close", "volume"],
    "used_library_methods": [],
    "assumptions": ["输入字段为按日期和证券对齐的日频面板。"],
    "warnings": ["该草稿未经回测验证，不构成投资建议。"]
  },
  "validation": {
    "status": "passed",
    "capability_catalog_version": "2026-07-01",
    "errors": [],
    "warnings": []
  },
  "meta": {
    "model_alias": "deepseek-v4-flash-260425",
    "prompt_version": "v1",
    "latency_ms": 2468
  }
}
```

| 响应字段 | 说明 |
|---|---|
| `generation_id` | 本次生成的服务端唯一标识；当前仅用于前端展示和问题定位，不是持久化资产 ID。 |
| `status` | `ready` 或 `rejected`。 |
| `factor.factor_name` | 因子方法名；与 `factor_code` 中函数名完全一致。 |
| `factor.factor_code` | 仅含一个实例方法定义；不含 `class`、`import`、Markdown 围栏或解释文字。 |
| `factor.description` | 模型对公式的自然语言解释，须视为草稿说明。 |
| `factor.used_fields` | 模型声明使用的字段；其中不能包含未登记字段。当前不保证该列表完整覆盖源码实际字段。 |
| `factor.used_library_methods` | 模型声明的库方法列表；MVP 不支持直接调用内置库方法，正常值应为空数组。 |
| `factor.assumptions` / `warnings` | 模型提供的假设和风险提示。前端应始终展示“未经回测验证”的风险提示。 |
| `validation.capability_catalog_version` | 当前本地字段/方法白名单版本。 |
| `meta.model_alias` | 本次实际请求使用的模型配置值。 |
| `meta.latency_ms` | 端到端供应商调用与本地校验耗时，单位毫秒。 |

## 4. 已拒绝的草稿

供应商成功响应但输出不符合受控因子契约时，HTTP 仍为 `200`，响应为 `rejected`。前端不得展示“回测”按钮；应展示简短错误并允许用户修改自然语言后重新生成。

```json
{
  "generation_id": "fg_31d9...",
  "status": "rejected",
  "factor": null,
  "validation": {
    "status": "failed",
    "capability_catalog_version": "2026-07-01",
    "errors": ["不允许的字段：get_data"],
    "warnings": []
  },
  "meta": {
    "model_alias": "deepseek-v4-flash-260425",
    "prompt_version": "v1",
    "latency_ms": 1810
  }
}
```

## 5. 代码约束

当前 AST 校验采用默认拒绝策略。通过校验的代码必须：

- 只含一个 `def`，函数名与 `factor_name` 一致，且第一个参数为 `self`；
- 仅访问 `self.open`、`self.high`、`self.low`、`self.close`、`self.volume`、`self.amount`；
- 仅调用 `abs`、`clip`、`diff`、`fillna`、`mean`、`median`、`min`、`max`、`pct_change`、`rank`、`rolling`、`shift`、`std`、`sum`、`where` 等面板方法；
- 仅使用局部赋值、返回、算术表达式和比较表达式（`==`、`!=`、`>`、`>=`、`<`、`<=`）；
- 能按 ResearchEngine 与回测一致的 `FactorLibrary` 包装规则完成 Python 编译。

下列内容会被拒绝：`import`、类/装饰器、`lambda`、`exec`/`eval`、`getattr`、文件/网络/子进程访问、双下划线属性、未登记字段与未登记方法调用。静态校验通过不代表因子经济有效、无未来函数或具有收益能力。

## 6. 前端接入流程

1. 用户填写研究假设；客户端生成新的 UUID 作为 `idempotency_key`。
2. 调用本端点，根据 `status` 渲染结果。
3. `ready`：展示代码、字段、说明与风险提示，允许用户复制或编辑。
4. 用户不修改代码时，调用因子回测：

```json
{
  "factor_code": "<factor.factor_code>",
  "factor_name": "<factor.factor_name>",
  "universe": "CSI500",
  "portfolio_type": "long_only",
  "rebalance_days": 20
}
```

5. 用户修改代码后，当前 MVP 没有独立“重新校验”端点；前端必须清除“已通过 AI 校验”标识，并在生产开放前接入重新校验/隔离执行能力。

## 7. HTTP 状态与重试

| HTTP 状态 | 场景 | 客户端处理 |
|---:|---|---|
| `200` | 已生成草稿；查看响应中的 `ready` / `rejected`。 | `ready` 可进入用户确认；`rejected` 提示调整自然语言后重试。 |
| `409` | 同一 `idempotency_key` 对应不同请求内容。 | 生成新的 UUID 后重新提交。 |
| `422` | 请求体字段、UUID、长度、频率或未知字段不符合 Pydantic 契约。 | 在前端修正请求，不自动重试。 |
| `503` | 未配置 Key，或供应商返回非超时错误（包括鉴权、模型或服务错误）。 | 显示“AI 服务暂不可用”；稍后重试并由运维检查服务端日志/配置。 |
| `504` | 供应商调用超过 20 秒。 | 可使用新的幂等键重试。 |

> 当前没有实现应用级 `401`、`403`、`429`；网关接入鉴权、权限与额度后将补充这些状态。

## 8. 火山方舟配置

所有配置仅由部署环境或密钥管理服务注入；浏览器请求中不得包含 Key、模型名或 Base URL。

| 环境变量 | 必填 | 默认值 / 用途 |
|---|:---:|---|
| `ARK_API_KEY` | 二选一 | 火山方舟 API Key；与官方 SDK 命名一致。 |
| `AI_FACTOR_API_KEY` | 二选一 | AI 因子服务专用 Key 名，优先级高于 `ARK_API_KEY`。 |
| `AI_FACTOR_BASE_URL` | 否 | `https://ark.cn-beijing.volces.com/api/plan/v3`。 |
| `AI_FACTOR_MODEL_ALIAS` | 否 | `deepseek-v4-flash-260425`。 |

调用会优先请求 `response_format.json_schema`。已验证的模型若明确拒绝该参数，服务自动降级为受控提示词 JSON，再由本地 JSON、AST 与编译校验把关；不会因该兼容性降级跳过本地校验。

## 9. 限制与后续工作

- 幂等记录仅存于单个 Python 进程内，进程重启或多实例部署后不共享。
- 没有用户身份、租户隔离、调用配额、成本计量或持久化审计。
- 生成服务不执行代码；现有回测接口仍需在生产部署为无网络、只读数据、CPU/内存/时限受控的子进程或容器。
- 内置因子库的组合调用、更多字段/运算符、编辑后重校验与自动修复尚未实现。
- 因子草稿必须经过回测、风险与数据可得性检查；平台不提供投资建议或收益承诺。
