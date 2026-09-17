# Technical Design：AI 回测解读与优化建议

## 1. 现状与差距

现有 `FactorBacktestResponse` 和 `StrategyBacktestResponse` 已提供结构化回测结果，但存在三类差距：

1. 返回的是数据结构，没有跨指标诊断、数据充分性判断和下一轮实验建议。
2. 原请求中的成本、复权和样本内/样本外口径未全部写入结果，需要调用方补充 `run_context`，缺失时必须保留未知语义。
3. 没有持久化 `backtest_id` 可供 AI 服务读取，MVP 需接受内联快照并标注来源。

## 2. 设计目标与非目标

### 设计目标

- 量化计算和模型表达解耦，所有关键数值先由确定性代码生成。
- 把可用事实、诊断规则和实验建议分别版本化。
- AI 输出可降级、可审计、可引用、可做黄金集评测。
- 不修改 `QuantCore` 的回测引擎或现有回测响应契约。

### 非目标

- 不实现参数搜索、策略源码修改、回测任务编排和结果资产持久化。
- 不在 AI 服务重复实现完整 MetricEngine；只对公开响应字段做规范化、交叉校验和必要派生。
- 不支持事件驱动订单因果分析。

## 3. 架构边界

```text
Web / API Client
  │  backtest result snapshot + run_context
  ▼
AI Backtest Interpretation API（过渡期可位于 researchengine.api）
  ├─ RequestValidator / ResultNormalizer
  ├─ EvidenceBuilder（确定性、无 LLM）
  ├─ DiagnosticEngine + versioned DiagnosticCatalog
  ├─ RecommendationEngine + versioned ExperimentCatalog
  ├─ PromptBuilder（只发送压缩证据和候选 ID）
  ├─ LLMProvider（复用 FEAT-016 服务端配置）
  ├─ GroundingValidator / ComplianceValidator
  └─ Audit / idempotency / quota
          │
          ├─ ready: grounded interpretation
          └─ provider/validation failure: deterministic fallback
```

| 模块 | 职责 | 不负责 |
|---|---|---|
| `interpretation_routes` | HTTP 契约、认证上下文和错误映射 | 计算量化指标、直接调用供应商 SDK |
| `result_normalizer` | 校验两类现有响应、日期排序、单位和缺失语义 | 修复失败回测或填补缺失数据 |
| `evidence_builder` | 生成规范证据、结果指纹和覆盖等级 | 自然语言、策略评级 |
| `diagnostic_engine` | 用版本化规则生成诊断候选 | 自由生成因果解释 |
| `experiment_catalog` | 将诊断映射为受控的可验证实验 | 自动修改和运行策略 |
| `prompt_builder` | 组装最小上下文和严格输出 Schema | 发送源码、持仓或完整曲线 |
| `grounding_validator` | 校验候选 ID、证据引用、枚举和允许参数 | 判断未来收益 |
| `interpretation_repository` | 幂等、审计、反馈和用量 | 回测结果资产存储 |

长期边界遵循 ADR-012：身份、密钥、额度、模型调用和审计属于 SaaS 应用层；ResearchEngine 提供确定性分析能力，QuantCore 不依赖 LLM SDK。过渡实现不得成为新的长期耦合。

## 4. 核心流程

1. 严格校验请求体大小、回测类型、现有响应 Schema、`error`、日期和幂等键。
2. 规范化浮点数、日期和缺失值；按字段白名单计算 `SHA-256` 结果指纹，排除展示顺序和无关元数据。
3. `EvidenceBuilder` 复算/交叉校验总收益、基准收益、回撤、年度与阶段统计，并汇总已知假设和覆盖缺口。
4. `DiagnosticEngine` 根据版本化阈值生成诊断候选；`RecommendationEngine` 从实验目录生成候选实验。
5. 若证据不足，直接返回 `insufficient`；否则将压缩证据摘要、候选 ID 和脱敏问题发送给 Provider。
6. Provider 按 JSON Schema 仅返回候选选择、排序、置信度和短解释，不得创建新事实、数值或实验参数。
7. `GroundingValidator` 校验所有 ID、引用、枚举和参数；`ComplianceValidator` 拒绝收益承诺、荐股、自动下单和无证据因果。
8. 校验失败或供应商不可用时使用确定性模板渲染；成功时数值仍由服务端从证据包注入最终响应。
9. 写入脱敏审计元数据后返回结果。

## 5. 核心数据模型

### 5.1 EvidenceItem

```python
class EvidenceItem(BaseModel):
    evidence_id: str
    category: Literal["identity", "coverage", "performance", "risk", "stability", "execution", "factor", "assumption"]
    label: str
    value: str | int | float | bool | None
    unit: str | None
    status: Literal["observed", "derived", "unknown", "not_applicable"]
    source_paths: list[str]
    definition_version: str
    limitations: list[str] = []
```

`source_paths` 指向输入快照字段，如 `metrics.max_drawdown` 或 `drawdowns[0].depth`。派生值必须记录公式和输入来源；`unknown` 不得携带伪默认值。

### 5.2 DiagnosticCandidate

```python
class DiagnosticCandidate(BaseModel):
    candidate_id: str
    code: str
    severity: Literal["info", "warning", "critical"]
    evidence_refs: list[str]
    safe_claim_template: str
    confidence: Literal["high", "medium", "low"]
    limitation_codes: list[str]
```

### 5.3 ExperimentCandidate

```python
class ExperimentCandidate(BaseModel):
    experiment_id: str
    trigger_codes: list[str]
    category: Literal["data_quality", "robustness", "cost", "risk", "execution", "factor", "portfolio"]
    primary_variable: str
    allowed_values: list[str | int | float]
    expected_direction: list[str]
    tradeoffs: list[str]
    validation_method: str
    pass_criteria: list[str]
    manual_only: bool = True
```

Provider 只能选择已有 `candidate_id` / `experiment_id`，可在限定长度内生成通俗解释。最终 API 由服务端把模板、证据值和模型排序合并。

## 6. 证据和诊断目录 v1

阈值是产品默认的“提醒触发器”，不是策略好坏的普遍真理；必须版本化并在评测集中校准。

| 代码 | 初始触发条件 | 诊断含义 | 候选实验 |
|---|---|---|---|
| `INSUFFICIENT_SERIES` | 有效净值点 `< 60` | 无法形成可靠解读 | 延长区间或补齐数据后重跑 |
| `SAMPLE_TOO_SHORT` | `60–251` 个有效点 | 结论受单一年度/市场阶段影响较大 | 延长样本并分阶段验证 |
| `NO_OUT_OF_SAMPLE` | `validation_scheme` 缺失或为 `in_sample` | 不具备泛化证据 | 固定参数，增加留出集或 Walk-forward |
| `COST_ASSUMPTION_UNKNOWN` | 任一核心成本未知 | 净收益可靠性不足 | 补齐佣金、印花税、滑点并做成本压力测试 |
| `ZERO_COST_ASSUMPTION` | 佣金或滑点明确为 0，且策略有换手 | 表现可能高估 | 用基线/悲观成本两档复跑 |
| `HIGH_TURNOVER` | 平均单边换手 `>= 0.10/日` | 策略对成本与执行敏感 | 单独放宽调仓周期，比较净收益、回撤与换手 |
| `DEEP_DRAWDOWN` | 最大回撤 `<= -0.20` | 资本曲线存在较深损失阶段 | 先做回撤阶段与基准/持仓对照，再测试单一风险约束 |
| `YEAR_CONCENTRATION` | 至少 3 个完整自然年、总收益为正，且最好一年的正对数收益占全部正对数收益 `>= 70%` | 表现可能依赖少数年份 | 分阶段/滚动窗口验证，不调参先确认稳定性 |
| `WEAK_FACTOR_SIGNAL` | 因子 `abs(IC) < 0.02` 且样本充分 | 线性截面预测力较弱 | 检查方向、滞后、去极值/中性化并做独立对照 |
| `WEAK_LAYER_MONOTONICITY` | 分层终值不满足主要方向单调 | 因子排序稳定性不足 | 检查分组、极值、行业偏置与持有期 |

缺少对应字段时不触发数值诊断，只生成覆盖警告。阈值配置不允许由客户端覆盖。

## 7. Provider 上下文与结构化输出

复用 FEAT-016 的服务端 Provider 抽象、Base URL、模型别名、超时和密钥管理。新的提示词域和模型别名独立版本化，避免因子生成与回测解读相互影响。

发送给模型的内容仅包含：

- 证据包中经白名单选择并四舍五入的摘要；
- 诊断候选与实验候选的 ID、标题和安全说明；
- 用户关注点和脱敏问题；
- 固定合规约束和 JSON Schema。

禁止发送策略/因子源码、证券代码和名称、持仓/订单/成交明细、完整净值曲线、用户/租户标识、供应商密钥和内部提示词版本内容。证券明细未来如需解释，必须使用本地聚合后的行业/风格证据。

## 8. 数据、审计与幂等

| 实体 | 关键字段 | 保留策略 |
|---|---|---|
| `backtest_interpretation` | ID、tenant/user、结果指纹、状态、模式、Schema/目录/提示词/模型版本、输入输出哈希、耗时、用量、错误码 | 审计元数据至少 90 天 |
| `interpretation_idempotency` | tenant、幂等键、请求哈希、interpretation ID、过期时间 | 24 小时 |
| `interpretation_feedback` | interpretation ID、有用性、原因、时间 | 按产品分析策略 |
| `evaluation_case` | 匿名样本 ID、期望证据/诊断、专家标签、版本 | 随版本长期保留 |

MVP 不保存完整回测快照；仅保存规范化哈希、证据包和解释结果。若调试需要短期保存原始请求，必须另设开关、脱敏且默认关闭。

## 9. 异常、安全与可观测性

- 结果快照和用户问题均视为不可信输入；Pydantic `extra=forbid`、大小限制、日期/NaN/Inf 校验和字符串清洗必须先于模型调用。
- Prompt 注入只能影响用户问题自由文本，不能修改系统约束、候选目录或 JSON Schema。
- Provider 采用连接与总超时、有限重试和熔断；失败优先降级，不能影响回测接口。
- 日志不记录完整 prompt、完整证据或供应商响应；错误中不泄露密钥、系统提示词和内部栈。
- 指标：请求量、ready/insufficient/fallback 比例、证据覆盖、各诊断触发率、引用校验失败率、供应商延迟/token/成本、用户反馈。
- 告警：引用校验失败率、fallback 比例或供应商错误率超过阈值；任何密钥扫描命中立即阻断发布。

## 10. 兼容、迁移与回滚

- 新端点和模块均为增量；现有 `/api/backtest/factor`、`/api/backtest/strategy` 请求与响应不变。
- 用 `AI_BACKTEST_INTERPRETATION_ENABLED=false` 关闭入口；关闭后 UI 隐藏按钮，原回测功能继续使用。
- 诊断目录和证据 Schema 升级保留旧版本渲染器；历史记录不按新阈值悄悄重算。
- Provider 变更不影响确定性证据和降级报告。
- SaaS 应用层就绪后迁移路由、身份、配额和审计；`EvidenceBuilder` 保持纯函数接口，可由 ResearchEngine 内部调用。

## 11. 测试策略

1. **单元测试**：规范化、指纹、每个证据公式、缺失语义、每条诊断阈值边界和实验映射。
2. **黄金测试**：手工构造净值/基准/年度/因子序列，验证结果精确到既定容差。
3. **属性测试**：日期乱序、重复、NaN/Inf、极端数值、空数组、超长序列和随机缺失字段。
4. **契约测试**：因子/策略响应 Schema、幂等、错误码、2 MiB/10,000 点限制和 `extra=forbid`。
5. **Grounding 测试**：未知 ID、新造数值、新造参数、无引用结论、收益承诺和因果词攻击均触发降级。
6. **隐私测试**：Provider mock 捕获请求，断言不存在源码、证券明细、完整曲线、身份和密钥。
7. **故障测试**：超时、限流、5xx、非 JSON、部分 JSON 和仓储失败；回测接口不受影响。
8. **专家评测**：30–50 个匿名回测样本，由至少 2 名评审标注事实正确性、风险优先级和实验可执行性；分歧样本复审。

## 12. 备选方案与风险

| 方案 | 结论 |
|---|---|
| 将完整回测 JSON 直接发送给 LLM | 实现快，但成本高、难复算、容易臆造数值和因果，不采用 |
| 只用规则模板，不使用 LLM | 最可信但交互僵硬；保留为降级路径，不作为唯一体验 |
| 让 Agent 自动改策略并循环回测 | 演示效果强，但权限、成本、过拟合和审计风险超出 MVP，另立 Feature |
| 先建设完整结果资产服务 | 长期合理，但会阻塞 Wave 1；MVP 用内联快照和指纹解耦 |

长期决策见 `../../05-技术决策/ADR-015-为什么AI回测解读采用证据先行架构.md`。
