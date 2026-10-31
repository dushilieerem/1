# 机构端与手机端 Agent 设计（v0.1）

| 项 | 内容 |
|---|---|
| 日期 | 2026-10-30 |
| 状态 | 首版落地中 |
| 前置 | [ADR-037 AI 能力统一路由层](../../技术决策/ADR-037-AI能力统一路由层.md)、[主观机构端需求 v1.1](/home/dev01/download/10.30主观机构李思博/Sunvalley_AI_Value_Investment_Requirements_v1.1.md)、[手机端 AI Agent 能力清单](/home/dev01/download/10.29手机端朱梦研/SVQuant-AI-Agent能力清单交付文档.md) |
| 代码 | `backend/ai/router/tasks/institution.py`、`backend/ai/router/tasks/invest.py`、`backend/services/institution/inst_service.py`、`backend/app/routers/invest_ai.py` |
| 模型 | OpenAI 兼容网关 `LLM_*`（内网 LiteLLM，默认 `deepseek-flash-yxd`） |

> 本文只描述 AI 能力如何接入、如何约束、如何验收；业务状态机与阈值在服务端代码中，不由模型决定。

---

## 1. 分层与边界

```text
业务（机构端 inst_service / 手机端 invest 路由）
  │  只调用 task_id + 已注入的结构化数据
  ▼
L2 ai/router  TaskSpec：prompt、temperature、max_tokens、validator、执行链
  ▼
L1 ai/gateway  OpenAI 兼容网关 / 火山 / 硅基流动 / RE
  ▼
模型：deepseek-flash-yxd（默认档位）
```

三条硬规则：

1. **AI 不改变业务状态**：研究审核、议案审批、风控阻断、授权、成交全部由服务端状态机执行；AI 只返回建议与解释。
2. **重大结论必须带证据 ID**：机构端辩论与审批包中的事实必须引用 `inst_evidence.id`；引用不存在的 ID 由 validator 拦截。
3. **确定性逻辑不用模型**：阈值、有效期、版本一致性、目标仓位、现金比例、授权校验、订单幂等全部用代码。

---

## 2. 机构端 Agent 映射

需求有 25 个 AI 岗位；首版不逐个建模型，而是按「输入/输出契约」收敛为 4 个 TaskSpec，其余岗位由确定性工具 + 模板承担。

| TaskSpec | 覆盖岗位 | 输入 | 输出 | 校验 |
|---|---|---|---|---|
| `inst.debate` | AI-12 看多 / AI-13 看空 / AI-14 主持 | 公司、研究版本、证据列表（含 id） | `{bull[], bear[], chair[]}`，每条含 claim/evidence_ids/confidence/falsifier/round | 三个 side 均非空；evidence_ids 必须存在于输入；缺失抛 `AiBadOutput` |
| `inst.research_memo` | AI-01/04/05/06/07/09/11 的研究汇总 | 六维结论、财务、估值、证据 | `{summary, evidence[], risks[], open_questions[]}` | JSON 对象；字段缺失补空 |
| `inst.risk_review` | AI-18 独立风控 | 议案快照、风险检查项、组合约束 | 同上 | 只建议；不改变 `inst_approval` |
| `inst.chairman_memo` | AI-17 Chairman 审议辅助 | 研究/辩论/风控/组合影响 | 同上 | 不给目标价、不生成订单 |

**由代码承担、不交给模型的岗位**：

- AI-02 机会发现筛选：SQL + 条件解析 + 人工立项。
- AI-08 治理核验：当前只展示框架与待核验清单，不编造个人履历。
- AI-15/16 组合配置：目标仓位、集中度、现金比例用计算。
- AI-19 合规审计：审计表 + 规则检查。
- AI-20/21 执行与对账：授权校验、幂等、SimBroker 全部代码。
- AI-22/23/24/25 投后：持仓快照、事件、退出议案；AI 只写解释。

**辩论的隔离上下文**：首版用同一模型但两次独立调用（bull / bear 分开 prompt），避免一次生成两边导致「自说自话」；后续可拆成两个 TaskSpec 或不同模型。

---

## 3. 手机端 Agent 映射

手机端能力清单有 8 个 Agent / 20 项能力；首版收敛为 6 个 TaskSpec。

| TaskSpec | 覆盖能力 | 输入 | 输出 | 合规 |
|---|---|---|---|---|
| `invest.intent` | F17 意图路由、F2 条件解析入口 | 用户 query | `{intent, slots, need_clarify}` | 命中红线直接 `compliance_block`，不进模型 |
| `invest.daily` | F1 日报、F19 复盘、F20 持仓解读 | 首页/组合结构数据 | 卡片 `{summary, sections}` | 只解释数据，不给买卖 |
| `invest.stock` | F3 多空、F21 对比、F22 公告解读、AI 一句话 | 个股 quote/technical/valuation/report/risks/news | 卡片 | 数据缺失必须写「待补充」 |
| `invest.portfolio` | F10 诊断、F24 穿透、F25 风险扫描 | 持仓、集中度、行业暴露 | 卡片 | 零调仓指令 |
| `invest.announcement` | F22 公告要点 | 标题 + 摘要 | 卡片 | 只做「发生了什么/影响/关注」 |
| `invest.condition` | F2 条件选股 | 自然语言条件 | `{conditions[], explain}` | 不输出推荐语 |

**卡片协议**：`{summary, sections[], disclaimer, meta.dataSource}`；`summary` 必填，`disclaimer` 与 `meta.dataSource` 缺失即拒绝渲染。

**调度层**：值守/推送（F9、F23）首版只做「收盘后事件日志」，不做实时推送；调度工程独立，不与 Agent 混。

---

## 4. 提示词与数据注入

### 4.1 机构端辩论

系统提示词（节选）：

```text
你是投资辩论助手。只输出 JSON，结构：
{"bull":[{"claim":"...","evidence_ids":[1],"confidence":0.6,"falsifier":"...","round":1}],
 "bear":[...],"chair":[...]}。
每条必须引用输入中存在的 evidence id；不给买卖建议、目标价或收益承诺。
```

用户消息：`{company, evidence:[{id,title,quote,source}], valuation}`。

校验器 `validate_debate` 做三件事：

- 三个 side 必须是非空数组；
- 每条 claim 非空；
- evidence_ids 与输入 ID 求交，丢失的丢弃；若全部丢失，该条仍保留但前端标记「无有效证据引用，不计入裁决」。

### 4.2 手机端卡片

系统提示词（节选）：

```text
只使用用户输入 JSON 中的数据，不得补造任何数字或事实；数据缺失时明确写“数据缺失/待补充”。
只输出 JSON：{"summary":"一句话结论","sections":[{"key","title","type","body"}],
"disclaimer":"AI 生成 · 非投资建议","meta":{"dataSource":"..."}}。
不写买卖建议、目标价、涨跌预测或收益承诺。
```

数据来自 `rules.build_stock` / `build_home` / `build_portfolio` 的确定性读模型；AI 只做解释，不做计算。

---

## 5. 合规与安全

### 5.1 手机端红线

前置关键词（命中即固定话术，不进模型）：

```text
买入、卖出、买点、卖点、目标价、会涨、会跌、保证收益、稳赚、必涨、
抄底、梭哈、满仓、加杠杆、自动交易、自动下单、代客理财、帮我下单…
```

后置只扫描真正越界的表达（避免把「不提供买入建议」误判）：`建议买入`、`建议卖出`、`目标价`、`保证收益`、`会涨到` 等。

固定话术：

> 我们不提供买卖点、目标价、涨跌预测、仓位指令或收益承诺，也不代客理财、不自动交易。可以改为：看估值与财务数据、看组合风险、设置关注事件。

### 5.2 机构端

- 提案人不得审批自己的议案；AI 不得修改政策阈值、不得生成真实订单。
- AI 输出落库需带：模型/任务 ID、议案与版本、政策版本、时间、真人确认状态（后续补 `ai_artifact` 表）。
- 重大未决事项（会计、治理、准入）AI 必须移交真人。

### 5.3 模型与密钥

- 统一走 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`；默认档位 `default`。
- 无 Key 时：手机端 AI 接口返回 503，不用 mock 伪装成 AI；规则摘要继续可用。机构端辩论回退到确定性模板并标注。
- 密钥只写在 `backend/.env`（不进 git）；`.env.example` 只留占位。

---

## 6. 失败与降级

| 情形 | 行为 |
|---|---|
| 未配置模型/Key | `AiNotConfigured` → 手机端 503；机构端辩论用模板 |
| 上游超时 | `AiTimeout` → 502/504；前端可重试 |
| 输出非 JSON | `AiBadOutput` → 502；机构端回退模板 |
| 证据 ID 全部无效 | 论点保留但标记无效；不计入裁决 |
| 数据缺失 | 提示词要求写「待补充」；不补造数字 |
| 输出命中红线 | 替换为固定话术，不展示模型原文 |

---

## 7. 评测

| 维度 | 指标 | 目标 |
|---|---|---|
| 意图路由 | 准确率 | ≥ 90% |
| 槽位 | 一次问清率 | 跟踪 |
| 证据引用 | 机构端论点引用有效率 | 100%（无效 ID 丢弃并标记） |
| 事实一致 | 结论与输入数据一致 | 100% |
| 合规 | 红线输出 | 0 |
| 延迟 | 首字/整卡 | 手机端 < 30s；机构端辩论 < 150s |
| 卡片 | 渲染成功率 | ≥ 99% |

首批评测集：手机端 `03.测评集设计.md` 的能力/鲁棒/安全/体验四象限；机构端以 `FR-DEB/APR/RES` 的验收点构造 20 条黄金用例。

---

## 8. 落地状态与下一步

| 能力 | 状态 | 位置 |
|---|---|---|
| 机构端辩论 | 已接入真实模型，证据 ID 校验 | `inst_service._ai_debate` |
| 机构端研究/风控/Chairman 一页纸 | TaskSpec 已注册，接口待接 | `ai/router/tasks/institution.py` |
| 手机端意图路由 | 已接入 | `/api/invest/ai/intent`、`/chat` |
| 手机端日报/个股/组合/公告/条件 | 已接入 | `backend/app/routers/invest_ai.py` |
| 手机端 UI 面板 | 个股/首页/组合已接入 | `frontend/invest/src/components/AiPanel.tsx` |
| 值守调度/推送 | 未做 | 下一阶段 |
| AI 产物落库与真人确认 | 未做 | 下一阶段（`ai_artifact`） |

**下一步**：

1. 机构端研究一页纸、风控复核、Chairman 摘要三个接口接到对应页面。
2. 增加 `ai_artifact` 表：任务、模型、输入哈希、输出、证据 ID、真人确认状态。
3. 手机端条件选股从「解析」走到「可执行筛选」，并标注口径。
4. 建立黄金评测集与回归脚本；每次换模型跑一遍。
