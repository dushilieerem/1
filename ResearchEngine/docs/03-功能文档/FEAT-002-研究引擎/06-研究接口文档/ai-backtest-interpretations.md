# AI 回测解读与优化建议 API

> 状态：受控 MVP，开发中。关联：[FEAT-020](../../FEAT-020-AI回测解读/README.md)。
>
> 本页描述当前已实现行为。端点不执行回测、不修改策略或因子、不自动选择参数，也不输出投资建议。

## 1. 概述

`POST /api/ai/backtest-interpretations` 接收一份已成功的因子或向量化策略回测快照，先在服务端构建可复算的证据包和诊断，再输出最多 5 条必须人工执行的下一轮实验建议。

未配置 AI Provider、Provider 不可用或其排序结果不符合约束时，端点仍返回确定性报告（`mode=deterministic_fallback`）。已有因子和策略回测接口不受影响。

```text
回测快照 + run_context
        ↓
净值与字段校验 → 证据计算 → 诊断目录 → 实验目录
                                            ↓
                         可选：Provider 仅重排既有诊断
                                            ↓
                  经证据引用的解读 / 确定性降级报告
```

## 2. 请求

### `POST /api/ai/backtest-interpretations`

请求体必须为 JSON，未知字段返回 `422`。`result` 应直接使用 [因子回测](backtest-factor.md) 或[策略回测](backtest-strategy.md)的成功响应；`error` 必须为 `null`。

```json
{
  "backtest_type": "strategy",
  "result": {
    "metrics": {"turnover": 0.0842, "sharpe": 1.3568},
    "equity_curve": [
      {"date": "2024-01-02", "value": 1000000.0},
      {"date": "2024-01-03", "value": 1012500.0}
    ],
    "benchmark_curve": [
      {"date": "2024-01-02", "value": 1.0},
      {"date": "2024-01-03", "value": 1.006}
    ],
    "error": null
  },
  "run_context": {
    "validation_scheme": "in_sample",
    "commission_rate": 0.0003,
    "stamp_tax": 0.001,
    "slippage_rate": 0.001
  },
  "focus": "robustness",
  "question": "下一轮最值得验证什么？",
  "idempotency_key": "8ecb2eb2-6f7f-4d64-93b2-7e63b34ff2a8"
}
```

| 字段 | 类型 | 必填 | 当前规则 |
|---|---|:---:|---|
| `backtest_type` | `factor` / `strategy` | 是 | 决定是否读取因子专属 `factor_analysis.ic_mean`。当前只面向向量化策略；事件回测专项解释未实现。 |
| `result` | object | 是 | 成功回测快照。`equity_curve` 必须按日期严格递增、净值为正的有限数值；最多 10,000 点，至少 60 点。 |
| `run_context` | object | 否 | 成本、样本外验证等未包含在回测响应中的已知条件。省略字段按 `unknown` 处理，不能以零替代。 |
| `run_context.validation_scheme` | string | 否 | 当前识别 `in_sample`；缺省或该值均触发“缺少样本外验证”诊断。 |
| `run_context.commission_rate` / `stamp_tax` / `slippage_rate` | number | 否 | 交易成本假设。任一缺失触发成本口径不完整；策略有换手且佣金或滑点为 `0` 时触发零成本提醒。 |
| `focus` | `overall` / `risk` / `robustness` / `factor` / `execution` | 否 | 默认 `overall`。当前主要用于 Provider 的候选排序，不会改变证据口径或绕过研究门禁。 |
| `question` | string/null | 否 | 1–500 字。仅在 Provider 已配置时作为不可信自由文本参与排序，不能要求模型新增事实、数值或建议参数。 |
| `idempotency_key` | UUID string | 是 | 单服务进程内幂等键。相同键、相同请求返回首次结果；同键、不同请求返回 `409`；重启或多实例后不共享。 |

`result.error` 非空时端点返回 `200/rejected`。不足 60 个有效净值点时返回 `200/insufficient`，不会调用 Provider。

## 3. 成功响应

```json
{
  "interpretation_id": "bi_6ec66e9c19bf4ca3a4eeb01e09b0c0f6",
  "status": "ready",
  "mode": "deterministic_fallback",
  "evidence": {
    "schema_version": "1.0",
    "result_fingerprint": "sha256:...",
    "coverage": "partial",
    "warnings": ["SAMPLE_TOO_SHORT", "NO_OUT_OF_SAMPLE"],
    "items": []
  },
  "interpretation": {
    "summary": "当前结果缺少样本外验证，优先验证稳健性后再讨论收益优化。",
    "findings": [],
    "experiments": []
  },
  "disclaimer": "本结果仅用于量化研究，不构成投资建议或收益承诺。",
  "meta": {
    "model_alias": "not_configured",
    "prompt_version": "v1",
    "diagnostic_catalog_version": "v1",
    "latency_ms": 8
  }
}
```

| 字段 | 说明 |
|---|---|
| `interpretation_id` | 本次请求的临时唯一标识，格式为 `bi_` 加随机值；当前不是持久化结果资产 ID。 |
| `status` | `ready`、`insufficient` 或 `rejected`。仅 `ready` 才包含发现和实验建议。 |
| `mode` | `llm_grounded` 表示已由 Provider 合规重排既有诊断；`deterministic_fallback` 表示完全由本地规则生成；`not_applicable` 用于 `insufficient` / `rejected`。 |
| `evidence` | 服务端计算的可追溯事实和缺失项；最终数值应以其中条目为准。 |
| `interpretation.findings` | 诊断结论，每项均含稳定候选 ID、证据引用、严重级别和置信度。 |
| `interpretation.experiments` | 最多 5 条按优先级排序的下一轮实验，均固定 `manual_only=true`。 |
| `disclaimer` | 前端必须始终展示，不能被用户问题或 Provider 文本替代。 |
| `meta` | 非敏感追溯信息；不返回 Key、原始 Prompt 或供应商原始响应。 |

### 证据对象

每个 `evidence.items[]` 都具有以下字段：

| 字段 | 说明 |
|---|---|
| `evidence_id` | 稳定引用 ID，例如 `risk.max_drawdown`。`findings[].evidence_refs` 与 `experiments[].evidence_refs` 必须引用此值。 |
| `category` | `identity`、`coverage`、`performance`、`risk`、`stability`、`execution`、`factor` 或 `assumption`。 |
| `value` / `unit` | 事实或派生值；比例单位为 `ratio`。不可计算时 `value=null`。 |
| `status` | `observed`（源响应存在）、`derived`（本地复算）、`unknown`（缺失）或 `not_applicable`。 |
| `source_paths` | 输入快照或上下文字段路径，如 `metrics.turnover`、`equity_curve`。 |
| `limitations` | 对该单项的适用性限制；当前 MVP 可能为空数组。 |

当前证据包括结果指纹、净值点数、区间总收益、最大回撤、年化收益/夏普/换手、同期基准收益、验证方案、三项成本假设，以及因子回测可用时的平均 IC。

### 诊断与实验建议

当前诊断目录版本为 `v1`，包含：`SAMPLE_TOO_SHORT`、`NO_OUT_OF_SAMPLE`、`COST_ASSUMPTION_UNKNOWN`、`ZERO_COST_ASSUMPTION`、`HIGH_TURNOVER`、`DEEP_DRAWDOWN` 和 `WEAK_FACTOR_SIGNAL`。

建议字段含义：

| 字段 | 说明 |
|---|---|
| `experiment_id` | 受控实验 ID，例如 `ADD_OUT_OF_SAMPLE`。 |
| `priority` | 1 为最高；存在样本长度、成本或样本外缺口时，相关研究有效性实验优先于收益调优。 |
| `hypothesis` / `primary_variable` | 要验证的研究假设及唯一主要变量。 |
| `expected_direction` / `tradeoffs` | 预期改善维度和可能代价，不是收益承诺。 |
| `validation_method` / `pass_criteria` | 对照方法及可检查的通过条件。 |
| `manual_only` | 始终为 `true`；客户端不得据此自动改代码、自动重跑或下单。 |

## 4. 数据不足与拒绝响应

### 数据不足

```json
{
  "status": "insufficient",
  "mode": "not_applicable",
  "evidence": {"coverage": "insufficient", "warnings": ["INSUFFICIENT"]},
  "interpretation": {"summary": "有效净值点少于 60，建议补齐数据后再解读。", "findings": [], "experiments": []}
}
```

### 拒绝

回测响应自身携带业务错误时，返回 `200/rejected`。此时 `interpretation=null`，调用方应先修复并重新执行原始回测。

## 5. HTTP 状态与客户端处理

| HTTP 状态 | 场景 | 客户端处理 |
|---:|---|---|
| `200` | 已得到 `ready`、`insufficient` 或 `rejected`。 | 按响应 `status` 渲染；只有 `ready` 展示发现与实验操作入口。 |
| `400` | 净值曲线超过 10,000 点。 | 缩小区间或降采样后重试；不要静默截断。 |
| `409` | 幂等键用于不同请求。 | 为新的逻辑请求创建新的 UUID。 |
| `422` | JSON 字段/枚举/UUID 不符合契约，或净值日期不递增、净值非正/非有限。 | 修正请求后再提交，不自动重试。 |
| `503` | `AI_BACKTEST_INTERPRETATION_ENABLED=false`。 | 隐藏入口或显示服务维护状态；原回测继续可用。 |

Provider 未配置或调用失败不会返回 `503`，而是以 `200/ready` 和 `mode=deterministic_fallback` 返回本地报告。

## 6. 前端接入流程

1. 用户获得成功回测结果后生成 UUID，并将完整结果快照和本次回测的成本/验证上下文提交。
2. `status=insufficient` 时只展示补数提示，不展示“优化策略”操作。
3. `status=rejected` 时展示原始回测错误，不展示实验建议。
4. `status=ready` 时按 `findings` 和 `experiments.priority` 展示；点击每项时使用 `evidence_refs` 展开本地证据。
5. 固定展示免责声明，并把“执行实验”实现为预填下一次回测参数的人工操作；不得自动提交回测。

## 7. 服务端配置与限制

| 环境变量 | 作用 |
|---|---|
| `AI_BACKTEST_INTERPRETATION_ENABLED` | 设为 `false` 时关闭新入口；缺省为启用。 |
| `AI_BACKTEST_INTERPRETATION_API_KEY` | 解读服务专用 Provider Key；未设置时依次回退 `AI_FACTOR_API_KEY`、`ARK_API_KEY`。 |
| `AI_BACKTEST_INTERPRETATION_BASE_URL` | Provider Base URL；未设置时回退 `AI_FACTOR_BASE_URL`，再回退到火山方舟默认地址。 |
| `AI_BACKTEST_INTERPRETATION_MODEL_ALIAS` | 模型别名，默认 `ark-code-latest`。 |

- 当前幂等为内存实现，未提供持久化审计、用户身份、租户隔离或调用配额。
- Provider 上下文仅传递关注点、用户问题和既有诊断 ID/标题；不发送源码、证券/持仓/订单明细、完整净值曲线或成本数值。
- 当前未实施全请求体 2 MiB 上限；调用方仍应只提交单个、必要的回测快照。
- 当前版本不覆盖年度集中度、分层单调性、行业归因、事件回测专项解释及专家评测门禁；这些将随 FEAT-020 后续迭代补充。
