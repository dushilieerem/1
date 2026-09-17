# gather_idea crew

Agent A：外网资讯 / 研报 / 论文 / 帖子 → **EvidencePack**（含 LLM 摘要）。

| 入口 | 说明 |
|------|------|
| 页面 | `/ai/gather`（登录后；顶栏 **AI** 也进这里） |
| API | `POST /api/agent/gather` |
| 设计 | `E:\SVQuant_docs\mvp_agent\Agent设计-A-信息搜集.md` |
| 实现说明 | `E:\SVQuant_docs\mvp_agent\AgentA-信息搜集-技术实现说明.md` |

## 模块

```text
schemas.py       I/O
gather_agent.py  编排 + 过滤成包 + LLM digest（失败回退规则）
web_sources.py   外网多站检索（均摊 / 单站失败继续 / 正文补抓）
pipeline.py      配额 skill=gather
```

`use_llm: true`（默认）时走 `.env` 的 `LLM_*`；失败自动规则摘要。不再读站内 `news_items`。
