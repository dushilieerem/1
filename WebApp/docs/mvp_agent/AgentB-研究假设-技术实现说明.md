# Agent B · 研究假设 — 技术实现说明

> 日期：2026-08-18  
> 范围：**仅 Agent B**（EvidencePack → HypothesisBundle / IdeaBundle）  
> 主入口：`idea_agent.run_idea` · API：`POST /api/agent/idea` · 页：`/ai/idea`  
> 需求稿：[`Agent设计-B-研究假设.md`](./Agent设计-B-研究假设.md)

---

## 1. 一次请求

```text
浏览器 POST /api/agent/idea  { pack, preference, max_ideas }
  → 鉴权 + 配额 skill=idea
  → idea_agent.run_idea
       ① _normalize_pack / _normalize_preference
       ② items 空 → gaps，不编造
       ③ _llm_ideas（失败则 _rule_ideas）
       ④ _filter_ideas：citation 必须 ⊆ 本包 items
       ⑤ 返回 bundle
```

B **不重新检索**。材料质量完全取决于 A 的包。

---

## 2. 现网曾有的问题（已修）

| 问题 | 后果 | 现网 |
|------|------|------|
| 送给 LLM 的上下文**没有** `pack.query.topic` | 假设容易跟着包内热门条跑偏，不扣用户原问题 | 已传入 `topic`，并要求紧扣问题 |
| item `snippet` 截成 220 字 | A 已补抓 1500～4000 字正文，B 几乎扔掉 | 提到约 900 字 |
| LLM items 无 `url` / `source_label` | 模型分不清论文/帖/资讯 | 已带上 |
| `preference.focus` 只进 JSON、系统说明未强调 | 偏题材时仍大量标可转 | **已写死 focus=factor**，页面不再露开关 |
| 规则弱回退一律 `convertible=true` + 固定 close/volume 套话 | 和设计稿「不可转须诚实」不一致 | 事件题不可转；弱回退标明未走 LLM |
| `max_tokens=2400` | 5 条带 factor_prompt 易截断 JSON | 提到 **4500** |
| 从证据扫年份当回测窗（Weaver 1991→1991–今天） | 时段像写死、与假设无关 | **已删**；validity 改为「哪段可能更好」的分析建议 |

---

## 3. 压缩上下文

`_compact_items`：最多 20 条；每条保留 id、title、snippet（≤900）、source_type、source_label、url、published_at。

`_llm_ideas` 另传入：digest、digest_bullets、gaps_from_pack、preference、topic。

---

## 4. 生成与校验

- LLM：`temperature=0.3`；解析 JSON `ideas[]`。  
- `_filter_ideas`：无合法 `citation_ids` 的整条丢掉。  
- `convertible=true` 但 `factor_prompt` &lt; 20 字 → 降为不可转。  
- 缺 `validity` 时**不**再补 2018～今天这类假窗；由 LLM 写 `why_window`（哪段可能更好）。  
- 下游检测页回测由人设（常近十年），**不必采用** B 的建议时段。

---

## 5. 规则弱回退

仅当 LLM 失败或 0 条有效 idea。用 bullets（或条目标题）扩写，**不编造新事实**。  
弱回退不给 1991–今天这类扫年窗；只提示制度题应看落地后样本。

---

## 6. 仍可优化（非补丁词表）

| 点 | 说明 |
|----|------|
| 已做 | 论文/研报优先送给模型；IPO/会议类降为不可转 |
| 已做 | C 侧要求按 prompt 写码，不要一律动量 |
| 已做 | focus 写死偏因子；validity 改为分析建议 |
| 中 | 空帖 gaps 仍依赖模型听话；页面已展示证据缺口 |
| 低 | 与 A 配比：包几乎全是资讯时，可转比例应下降 |

---

*仅用于量化研究假设整理，不构成投资建议。*
