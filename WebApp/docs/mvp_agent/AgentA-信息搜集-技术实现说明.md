# Agent A · 信息搜集 — 技术实现说明

> 日期：2026-08-18（检索口径：无站内库、本题短语、论文过滤、PDF 前几页、帖子走 360 优先）  
> 范围：**仅 Agent A**（外网搜集 → 证据包 → 摘要）  
> 主入口：`gather_agent.run_gather` · 外网：`web_sources.py` · API：`POST /api/agent/gather` · 页：`/ai/gather`

---

## 1. 一次请求从头到尾

以问题为例：

> 「金工和学术现在还在盯哪些量价或微观结构方向？」  
> 时间窗：`3y` · 条数：20 · 四类全开 · `use_llm=true`

```text
浏览器 POST /api/agent/gather
  → api_server 鉴权 + run_gather_pipeline（扣配额 skill=gather）
  → gather_agent.run_gather(body)
       ① normalize_request
       ② _window_bounds
       ③ web_sources 四类外网（无站内库）
       ④ enrich_snippets（短摘要补抓正文）
       ⑤ _filter_window / _dedupe / _rank / _take_balanced
       ⑥ _llm_digest 或 _rule_digest
       ⑦ 组装 EvidencePack 返回
  → 前端展示 + session 历史
```

关键文件：

| 文件 | 作用 |
|------|------|
| `gather_agent.py` | 编排、过滤成包、摘要 |
| `web_sources.py` | 外网适配器（多站均摊 / 单站失败继续） |
| `pipeline.py` | 配额记账 |
| `AgentGatherPage.tsx` | 表单与展示 |

**边界**：A **不再**读本机 `news_items` / `list_news`。资讯、研报、论文、帖子全部外网检索。

---

## 2. 模块①：请求规范化 `normalize_request`

**干什么**

- `topic` 必填，最长约 240 字。  
- `themes`：兼容入参，**当前不参与检索**（站内题材库已关闭）。  
- `sources`：`news/report/paper/post` 四个布尔，默认 true。  
- `max_items`：1～50。  
- `time_window`：前端默认常为 `3y`。  
- `use_llm`：是否做 LLM 摘要。

**例子**

```json
{
  "topic": "金工和学术现在还在盯哪些量价或微观结构方向？",
  "themes": [],
  "time_window": { "preset": "3y" },
  "max_items": 20,
  "sources": { "news": true, "report": true, "paper": true, "post": true },
  "use_llm": true
}
```

---

## 3. 模块②：时间窗 `_window_bounds`

把 `preset` 映射成 `[start, end]`（东八区「今天」为 end）：

| preset | 天数（约） |
|--------|------------|
| 7d / 14d / 30d / 60d / 90d / 180d | 对应天数 |
| 1y / 2y / 3y / 5y / 10y | 365×N |
| all | 极大，近似不限 |

**对成包的影响**

- **资讯 / 研报 / 帖**：有 `published_at` 的，窗外条目会被 `_filter_window` 丢掉。  
- **论文**：`source_type=paper` **不做短窗裁剪**（经典文献往往早于「近 3 年」）。

---

## 4. 模块③：外网渠道 `web_sources`（核心）

每类返回 `(items[], warnings[])`。  
原则：

1. **多源均摊**：各站先分桶，再用 `_round_robin_merge` 轮询合并，避免东财等单一源占满配额。  
2. **单站失败继续**：某站反爬 / 超时只写 `warnings`，其它桶照常合并。  
3. **短摘要补正文**：`enrich_snippets` 对过短 snippet 再抓页面正文（单条失败不影响其它）。

### 4.1 检索计划（概念词）

| 函数 | 作用 |
|------|------|
| `search_tokens` | 从问题抽短概念 + 中英映射 |
| `distinctive_phrases` | 从原句抽本题短语（不按主题写 if） |
| `cn_search_queries` | 用上述短语组中文查询（最多约 8 组） |
| `paper_query` | 英文论文查询（动量/反转等有模板） |

### 4.2 资讯 `search_news_live`

分桶后轮询：

1. 东财全文搜索（软上限，不独占）  
2. 东财多栏目列表（短词过滤）  
3. DDG / 必应 `site:`：见闻、财联社、新浪、一财、证时、同花顺、中证等（**每站独立 try/continue**）

### 4.3 研报 `search_reports`

1. 东财 `researchReport`（软上限）  
2. 公开聚合：`金工/因子 研报`、hibor 等；先必应、空再 DDG，标题需像研报才收。

### 4.4 论文 `search_papers`

四库分桶再轮询：**OpenAlex / Crossref / arXiv / Semantic Scholar**。  
英文查询走 `paper_query`（量价/微观结构等有专用模板）。  
入库前用 `_paper_on_topic` 丢掉高引但非资产定价/因子类论文。OpenAlex 按相关度而非引用量排序。

### 4.5 帖子 `search_posts`

机制（不按主题写 `if 隔夜 / VPIN`）：

1. `distinctive_phrases` 从原句抽本题短语。  
2. 检索引擎：**360 搜索优先**（`data-mdurl` 还原真实 URL），必应中文常把「隔夜/质量/订单流」带到百科、菜谱、快递，junk 不当成功。必应作兜底。DDG 握手常超时，帖子通道不等它。  
3. **只收社区站**：聚宽 / BigQuant / 知乎 / 雪球 / 米筐 / 优矿 / 股吧 / CSDN 等。  
4. 标题+摘要必须命中本题短语；不能只因为写了「因子/量化」就进包。宁可 `gaps` 写空，也不拿入门帖充数。

资讯/研报的中文主检索词同样走本题短语。资讯/研报的通用网页搜索在必应空结果时也会试 360。

### 4.6 正文加长 `enrich_snippets`

- 条目摘要过短时补抓：网页 HTML 正文，或 **PDF 前几页**（`pypdf`；arXiv / 开放获取 `pdf_url` / 直链 `.pdf`）。  
- 论文优先占用抓取配额；目标摘要量级约 1500～4000 字（引言级，非整本）。  
- 付费墙 / 扫描版 PDF / 无开放获取链仍可能只有题录或短摘要。  
- 单条失败静默跳过，不影响其它条目。

### 4.7 条数

`run_gather` 里每通道先捞：

```text
per = max(8, min(24, max_items // 2 + 6))
```

例如 `max_items=20` → `per≈16`，四类 raw 可能到几十，再成包截断。

HTTP：国内站优先直连，海外/失败再走代理（如 `127.0.0.1:7897`）。

---

## 5. 模块④：过滤成包

### 5.1 `_filter_window`

- paper：一律保留。  
- 其它：无时间戳 → 保留；有时间戳 → 必须落在 `[start, end]`。

### 5.2 `_dedupe`

按标题键或 URL，同键留更新的一条。

### 5.3 `_rank`

相关度：主题片段、tokens 命中等 + 论文/研报/帖略加权 + 轻微时效加权。

### 5.4 `_take_balanced`

先按来源桶各取至少 2 条，再按总分填满 `max_items`，避免全是资讯。

### 5.5 `_to_evidence_item`

统一成包内 item：`id`、title、snippet、url、source_type、source_label、relevance 等。

---

## 6. 模块⑤：摘要 `_llm_digest` / `_rule_digest`

**Digest（`digest`）**：整包中文总述，给人和下游 Agent B 读「这批材料在讲什么」。理想 120～400 字。页面上叫「资料汇总」。

**Digest bullets（`digest_bullets`）**：3～8 条要点，每条带 `item_ids` 挂回包内证据。页面上叫「要点」。LLM 失败时规则摘要会用标题凑要点。

LLM 开且有 items 时：最多约 20 条的 id/标题/snippet 送给模型；失败 → `rule_fallback`。

---

## 7. 模块⑥：最终发出的 EvidencePack

`POST /api/agent/gather` 成功时返回的就是这份包（再加一层 HTTP 包装不影响字段）。

| 字段 | 含义 |
|------|------|
| `ok` | 本轮是否成功成包 |
| `pack_id` | 证据包 ID，后续 B 用它引用 |
| `query` | 实际检索条件回显：`topic` / `themes` / `time_window` / `sources` / `max_items` / `use_llm` / `digest_mode` |
| `items[]` | 成包条目（核心材料） |
| `items[].id` | 条目 ID，如 `web_news:…` / `web_paper:…` |
| `items[].source_type` | `news` / `report` / `paper` / `post` |
| `items[].title` | 标题 |
| `items[].snippet` | 摘要或补抓的正文片段 |
| `items[].url` | 原文链接 |
| `items[].published_at` | 发布时间（论文常为年份-01-01） |
| `items[].source_label` | 来源展示名（见闻/arXiv/聚宽…） |
| `items[].relevance` | 与问题的相关分 0～1 |
| `digest` | 总述，见上 |
| `digest_bullets[]` | `{text, item_ids}` 要点 + 引用 |
| `citations[]` | 给前端/B 的精简引用列表 `{id, label, url}`，与 items 对应 |
| `gaps[]` | 某大类开了但成包为 0，如「帖子源本轮无命中」 |
| `warnings[]` | 单站失败、反爬、digest 回退等，不阻断成包 |
| `stats.retrieved` | 过滤前捞到的条数 |
| `stats.after_dedupe` | 去重后 |
| `stats.returned` | 最终进包条数 |
| `stats.source_counts` | 成包后来源配比 |
| `stats.elapsed_ms` | 耗时 |
| `stats.digest_mode` | `llm` / `rule` / `rule_fallback` / `rule_forced` |
| `stats.tokens_in` / `tokens_out` / `llm_model` | 摘要模型用量（规则摘要时为 0） |

前端：展示 + `pushGatherHistory`；可带 pack 进入后续「研究假设」步骤。

---

## 8. 端到端数值例子（示意）

| 阶段 | 大约 |
|------|------|
| raw（四类外网） | 几十条量级 |
| 窗裁 + 去重后 | 略少 |
| 成包 returned | 16～20 |
| 来源混合 | 轮询后东财占比下降，其它站更容易进包 |

耗时：多站串行拉取 + 正文补抓，常 **数十秒～两分钟**（代理与 DDG 影响大）。

---

## 9. A 可继续优化清单

| 优先级 | 点 | 为何 |
|--------|----|------|
| 已做 | 本题短语 + 帖子 360 优先 | 避免「异象→因子异象 衰减」和必应 junk 充数 |
| 不做（现阶段） | 第五大类「财报」 | 与研报不同；个股财报海量且算因子仍走 RE 字段。盈利质量类问题用现有研报/论文/帖即可。公司级财报适配器以后再说 |
| 中 | 领域过滤 | 挡「行业量价齐升」、会计「盈利质量」盐选等进包 |
| 中 | 并行与超时 | 四类串行仍可能 1～3 分钟 |
| 中 | 正文抽取站点特化 | 见闻/财联社等专用解析 |
| 低 | 适配器注册表 | 加站不改 `run_gather` 主干 |
| 不做 | 按主题无限加关键词 if | 会永远补丁化；空帖应记 gaps |

---

*本文描述当前 WebApp 中 Agent A 实现，便于评审优化；不构成投资建议。*
