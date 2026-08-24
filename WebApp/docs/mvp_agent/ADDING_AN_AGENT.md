# 如何新增一个 Agent / Crew

> **包名**：`backend/ai/`  
> **关联**：[`AI-Agent目录整理方案.md`](./AI-Agent目录整理方案.md) · [`AI平台-宏观需求与架构.md`](./AI平台-宏观需求与架构.md)

---

## 1. 代码加在哪

| 你要加的东西 | 路径 |
|--------------|------|
| 新**产品线**多智能体（如搜集→idea） | `ai/crews/<crew_name>/` |
| 跨 crew 共用工具 | `ai/crews/_shared/` |
| 新 **Skill**（能力原子，多角色复用） | `ai/runtime/skills.py`（或日后 `skills/<name>.py`） |
| 换/加 **模型供应商** | `ai/gateway/`（`ark_chat.py` / `llm_client.py`） |
| 额度、Run 记账 | `ai/runtime/store.py` |
| 入口 API | `api_server.py` 里挂路由，调用 `ai.crews...` 或 `ai.runtime.runtime.start_run` |

**不要**再往 `services/` 根目录丢 `agent_xxx.py`。  
`services/agent_*.py` 仅保留兼容转发。

---

## 2. 推荐流程（新 crew）

```text
1. 需求/边界文档（摸底）     docs/mvp_agent/…
2. 建包目录                  ai/crews/<name>/
3. 写 schemas（输入输出契约） schemas.py
4. 写 agent / pipeline       xxx_agent.py · pipeline.py
5. 需要 LLM 时调网关         from ai.gateway.llm_client import …
6. 需要额度时走 store        from ai.runtime import store as agent_store
7. 挂 API                    POST /api/… → pipeline
8. 前端入口（可选）          pages/… 
9. 冒烟                      登录后打一枪接口
```

### 目录模板

```text
ai/crews/my_crew/
  __init__.py          # 导出 run_my_crew
  README.md            # 一句话职责 + 输入输出
  schemas.py           # TypedDict / dataclass
  pipeline.py          # 串联多个 agent
  xxx_agent.py         # 单角色
```

### `__init__.py` 示例

```python
"""my_crew：一句话说明。"""
from ai.crews.my_crew.pipeline import run_my_crew

__all__ = ["run_my_crew"]
```

### 本周例子：`gather_idea`

已占位：`ai/crews/gather_idea/`。  
实现时按 [`信息搜集与idea生成-边界摸底.md`](./信息搜集与idea生成-边界摸底.md) 的证据包 / ideas 契约写 `schemas.py` + `pipeline.py`。

---

## 3. 和现有社区 crew 的关系

| 现成能力 | 位置 |
|----------|------|
| 发帖 Writer/Critic/Router | `ai/runtime/orchestrator.py` + `ai/crews/community/` 导出 |
| Skills | `ai/runtime/skills.py` |
| 指标可信度 | `ai/crews/_shared/metrics_trust.py` |
| 启动入口 | `ai.runtime.runtime.start_run` ← `POST /api/agent/runs` |

社区逻辑暂时仍在 `runtime/orchestrator.py`（与 skills 耦合紧）；**新产品线请开新 crew 包**，不要继续把所有人塞进 orchestrator。

---

## 4. 导入约定

新代码请写：

```python
from ai.runtime.store import ensure_ai_usage_schema
from ai.gateway.ark_chat import chat
from ai.crews.community import run_community_crew
```

不要再 `from services.agent_*`（旧壳文件已删除）。

---

## 5. 自检清单

- [ ] 文件在 `ai/` 下，不在 `services/` 根  
- [ ] 输入输出有文档/schemas  
- [ ] 调外部模型只经 `ai/gateway`  
- [ ] 敏感数据 / L3 不进 Prompt（对齐 AI 平台宏观文档）  
- [ ] API + 至少 1 次人工冒烟
