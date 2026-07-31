# Product Requirements：AI 自然语言因子生成 API

## 用户故事

1. 作为研究员，我希望输入一句自然语言假设，并得到可读、可编辑、可回测的因子函数草稿。
2. 作为 Web 应用，我希望获得稳定的结构化响应，以展示代码、使用字段、假设、警告和校验状态。
3. 作为平台管理员，我希望 LLM 密钥、供应商选择、调用额度和审计记录均由服务端控制。

## 主流程

```text
用户填写自然语言 + 可选研究上下文
        ↓
Web 应用调用 AI 生成 API（携带用户身份与幂等键）
        ↓
AI 服务加载版本化能力目录和受控提示词，调用第三方 LLM
        ↓
JSON Schema 解析 → AST 静态校验 → 生成审计记录
        ↓
返回因子草稿、解释和校验结果给 Web
        ↓
用户查看/编辑/确认 → 调用既有 /api/backtest/factor
```

## API 契约

### `POST /api/ai/factor-generations`

该端点归属 Web/SaaS 应用层的 AI Research Service，不归属 `ResearchEngine`。身份由网关注入，客户端不得提交 `provider_api_key`、`system_prompt` 或任意供应商地址。

**请求示例：**

```json
{
  "prompt": "生成一个衡量过去20个交易日上涨动量、同时偏好成交量放大的日频选股因子",
  "context": {
    "universe": "CSI500",
    "frequency": "1d",
    "allowed_library_names": ["technical_indicators"],
    "preferred_factor_name": "volume_confirmed_momentum_20"
  },
  "idempotency_key": "8ecb2eb2-6f7f-4d64-93b2-7e63b34ff2a8"
}
```

| 字段 | 必填 | 规则 |
|---|---:|---|
| `prompt` | 是 | 1–2,000 个字符；仅描述研究假设，不承诺收益或交易建议 |
| `context.universe` | 否 | 仅用于生成解释和后续回测建议，不改变因子代码数据权限 |
| `context.frequency` | 否 | MVP 固定 `1d`；其他值返回 `422` |
| `context.allowed_library_names` | 否 | 必须为服务端登记的内置库子集；缺省使用部署默认目录 |
| `context.preferred_factor_name` | 否 | 必须为 Python 标识符；服务端仍会校验或改写冲突名称 |
| `idempotency_key` | 是 | UUID；相同租户和键在 24 小时内返回同一生成记录，不重复计费 |

**成功响应示例：**

```json
{
  "generation_id": "fg_01J...",
  "status": "ready",
  "factor": {
    "factor_name": "volume_confirmed_momentum_20",
    "factor_code": "def volume_confirmed_momentum_20(self, window=20):\n    momentum = self.close.pct_change(window)\n    volume_ratio = self.volume / self.volume.rolling(window).mean()\n    return momentum * volume_ratio",
    "description": "以20日价格动量乘以相对成交量，分数越高表示上涨且成交放大。",
    "used_fields": ["close", "volume"],
    "used_library_methods": [],
    "assumptions": ["close 与 volume 为日频、按日期和证券对齐的面板数据。"],
    "warnings": ["成交量异常和停牌会导致缺失值；请在回测中检查换手和分层表现。"]
  },
  "validation": {
    "status": "passed",
    "capability_catalog_version": "2026-07-01",
    "errors": [],
    "warnings": []
  },
  "meta": {"model_alias": "factor-generator-default", "prompt_version": "v1", "latency_ms": 1260}
}
```

`factor_code` 必须是恰好一个实例方法定义，不包含 class、import、Markdown 代码围栏或任何说明文字。Web 在用户确认后按下列方式调用已存在的回测端点：

```json
{
  "factor_code": "<factor.factor_code>",
  "factor_name": "<factor.factor_name>",
  "universe": "CSI500",
  "rebalance_days": 20,
  "portfolio_type": "long_only"
}
```

### 错误与状态

| HTTP / `status` | 场景 | Web 行为 |
|---|---|---|
| `200` / `ready` | 已生成且静态校验通过 | 展示代码并允许编辑、确认回测 |
| `200` / `rejected` | 模型输出无法解析或违反代码策略 | 展示简短原因，允许用户重试；不得提供回测按钮 |
| `400` | `prompt` 为空或超长 | 引导用户修正输入 |
| `401/403` | 未登录、无 AI 权限 | 跳转登录或提示套餐/权限 |
| `409` | 幂等键与请求内容不一致 | 客户端生成新键后重试 |
| `429` | 调用额度或速率超限 | 显示重试时间或升级入口 |
| `502/503/504` | 供应商失败、不可用或超时 | 不泄露供应商原始错误；允许安全重试 |

## 业务规则与边界

- 生成结果是“研究草稿”，不是已验证因子、投资建议或交易指令；响应必须包含这一语义的 `warnings`。
- 模型只能使用服务端发布的字段/方法能力目录；目录需标注数据频率、可得性、弃用状态和可调用签名。
- 代码仅允许一个 `def name(self, ...)`；禁用 decorators、import、lambda、class、`exec`/`eval`、反射、文件/网络/子进程、双下划线属性和未登记调用。
- 静态校验通过仅表示符合语法和受控 API，不能保证经济含义、无未来函数或回测收益；实际执行仍受 ResearchEngine 的运行错误处理和生产沙箱约束。
- Web 对代码的任何编辑都会使原 `validation` 失效；必须重新调用校验接口（MVP 可复用同端点的 `validate_only` 内部能力）后才能启用回测。
- 调用第三方模型前必须进行敏感信息过滤。MVP 不发送用户标识、API Key、未公开行情、持仓、交易账户或原始回测结果；发送内容限自然语言、能力目录和非敏感生成上下文。

## 非功能要求

- 首期接入字节火山方舟 AgentPlan API，默认模型为 `ark-code-latest`；API Key 仅在服务端密钥管理中保存，日志、响应和异常均不得出现密钥或完整供应商请求头。
- 95% 正常生成请求在 10 秒内完成；供应商调用超时上限 20 秒。
- 每租户默认 10 次/分钟、日额度由套餐配置；幂等重试不重复扣减。
- 每条生成记录至少保留 90 天的哈希化审计元数据；原始 prompt 是否留存由数据保留策略单独配置，默认 30 天后删除。
- 能力目录和提示词模板必须版本化；相同输入、模型别名、模板和目录版本可追溯到同一生成条件，但不承诺第三方模型输出完全确定。

## 验收标准

| 编号 | 可测试的验收条件 |
|---|---|
| AC-01 | 合法自然语言请求返回 JSON 结构化因子草稿；代码可被既有 `_wrap_factor_code` 包装，并能通过语法编译。 |
| AC-02 | 返回的 `factor_code` 仅含一个实例方法；含 import、文件访问、网络访问、`exec`、双下划线属性或未登记字段的模型输出均为 `rejected`，不返回可回测代码。 |
| AC-03 | 用户确认后，将响应中的 `factor_code`/`factor_name` 原样提交到既有因子回测 API，能进入其既有成功或业务错误流程，无需修改请求格式。 |
| AC-04 | 第三方模型 API Key 仅从服务端配置读取，HTTP 请求、响应、审计日志和错误中均不含该密钥。 |
| AC-05 | 相同租户、相同幂等键、相同请求在有效期内不重复调用供应商且返回相同 `generation_id`；内容不同返回 `409`。 |
| AC-06 | 超额、供应商超时和供应商 5xx 分别返回 `429`、`504`、`502/503`，且不泄露内部提示词或供应商原始异常。 |
| AC-07 | 审计记录能关联模型别名、提示词版本、能力目录版本、输入/输出哈希、校验结果、调用量和耗时。 |
