# AI / Agent 后端目录整理方案

> **日期**：2026-08-17  
> **状态**：阶段 B～D 已落地（2026-08-17）——代码在 `backend/ai/`，`services/agent_*` 等为兼容转发  
> **新 Agent 指南**：[`ADDING_AN_AGENT.md`](./ADDING_AN_AGENT.md)

---

## 1. 现状（是的，有点乱）

`WebApp/backend/services/` 约 30+ 文件挤在一层，大致混了四类：

| 类型 | 例子 |
|------|------|
| **Agent / AI** | `agent_*.py`、`ark_chat.py`、`llm_client.py`、`speech_transcribe.py` |
| **业务 store** | `auth_store`、`detect_store`、`news_store`、`community_store`… |
| **领域工具** | `dashboard_store`、`market_data_bff`、`factor_trial`… |
| **基础设施** | `db.py`、`env_config.py`、`lan_http.py` |

Agent 相关已用 `agent_` 前缀，但和资讯/检测同级，**新 crew（搜集→idea 等）再加文件会更难找**。  
前端侧相对清楚：`/ai/chat`、`/factor/ai`、`/strategy/ai`；乱主要在 **backend/services**。

文档侧也有两摊：`docs/mvp_agent/`（样例/摸底）与业务 API 文档——可接受，但实现目录要先收。

---

## 2. 目标结构（建议）

```text
backend/
├── services/                 # 业务与基础设施（保持，少动）
│   ├── db.py
│   ├── env_config.py
│   ├── *_store.py            # 各域持久化
│   ├── news_*.py
│   └── ...
│
└── ai/                       # ★ 新增：所有大模型 / Agent 能力
    ├── __init__.py
    ├── gateway/              # 模型网关
    │   ├── ark_chat.py       # ← 现 services/ark_chat.py
    │   ├── llm_client.py     # ← 现 services/llm_client.py
    │   └── speech.py         # ← speech_transcribe.py
    ├── runtime/              # 运行时与编排
    │   ├── store.py          # ← agent_store（额度/run 持久化）
    │   ├── runtime.py        # ← agent_runtime
    │   ├── orchestrator.py   # ← agent_orchestrator
    │   └── skills.py         # ← agent_skills（或再按 crew 拆）
    ├── crews/                # 按产品线拆多智能体
    │   ├── community/        # 发帖 Writer/Critic/Router
    │   ├── gather_idea/      # 信息搜集 → idea（本周文档）
    │   └── _shared/          # metrics_trust 等共用
    └── README.md             # 本目录约定
```

**原则：**

1. **`ai/` 只放「会调模型 / 编排 Agent」的代码**；纯 CRUD store 仍留 `services/`。  
2. **一个 crew 一个子包**，避免再堆 `agent_xxx2.py`。  
3. **网关与编排分离**：换模型供应商只动 `gateway/`。  
4. **兼容期**：`services/agent_*.py` 可暂时 `from ai.xxx import *` 再导出，api_server 旧 import 不炸。

---

## 3. 迁移节奏（推荐）

| 阶段 | 做什么 | 风险 |
|------|--------|------|
| **A. 文档定稿** | 本方案 + ADDING_AN_AGENT | ✅ |
| **B. 建包 + 薄封装** | `ai/` + `services/*` re-export | ✅ |
| **C. 搬 gateway** | ark_chat / llm_client / speech | ✅ |
| **D. 搬 runtime** | store / runtime / orchestrator / skills / metrics_trust | ✅ |
| **E. 拆 crews** | community 导出包；gather_idea 占位 | ✅ 起步（orchestrator 仍在 runtime，新产品线开新包） |

**不建议**：一口气物理移动 10+ 文件且不留 re-export——容易打断试用口。

---

## 4. 与「信息搜集 → Idea」的关系

新子模块**直接落在** `ai/crews/gather_idea/`，不要继续往 `services/` 根上堆：

```text
ai/crews/gather_idea/
  ├── __init__.py
  ├── gather_agent.py      # 信息搜集
  ├── idea_agent.py        # idea 生成
  ├── pipeline.py          # A→B 串联
  └── schemas.py           # 证据包 / ideas 契约
```

实现可等需求正文（周二～周四）；**目录先占位也可**（空包 + README）。

---

## 5. 前端（可选，非急）

当前够用。Agent 变多后再考虑：

```text
frontend/src/
  lib/ai/          # chat API、agent runs 客户端
  pages/ai/        # AiChatPage 等
  features/agents/ # 若有共用 UI
```

本日**不搬前端**。

---

## 6. 结论（回答「需不需要整理」）

| 问题 | 答案 |
|------|------|
| 现在乱吗？ | **有点乱**：AI 与业务 store 同层，扩展 Agent 会更挤 |
| 要不要整理？ | **要**，按上面 `ai/` 分层 |
| 今天大搬家吗？ | **先不定搬**；本日交方案；建空包可选；真搬走阶段 B～E |
| 和新 Agent？ | 新代码按目标目录写，避免继续污染 `services/` 根 |

---

## 7. 待你拍板

1. 包名用 `ai/` 还是 `agents/`？（建议 **`ai/`**，含网关不只 Agent）  
2. 是否本周内做完阶段 B（建包 + re-export）？还是等搜集→idea 开工时一起做？
