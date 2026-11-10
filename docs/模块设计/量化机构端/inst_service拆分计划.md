# `inst_service.py` 拆分计划

> 背景：`backend/services/institution/inst_service.py` 目前 6,848 行、约 120 个函数，
> 同时承担公司池、研究、辩论、议案、审批、授权、执行、持仓、AI、审计。
> 三个 Agent 中两个在改它，review 与冲突成本最高的就是这里。

## 目标结构

```
services/institution/
  common.py         JSON/格式化小工具（已完成）
  stages.py         六阶段状态机：STAGE_*、阶段推进、门禁/流转记录（已完成）
  repo.py           数据访问（已有，保持）
  company_service.py   公司池、行业映射、搜索
  research_service.py  立项、研究生成、定稿门禁、版本锁定
  debate_service.py    多空辩论
  proposal_service.py  议案、三关审批（合伙人/风控/Chairman）
  execution_service.py 授权、预检、执行、对账、异常
  portfolio_service.py 持仓、监控、论点、退出
  ai_service.py        AI 备忘/对话/角色建议（只产建议，不改状态）
  audit_service.py     审计与 Agent 提示词管理
  inst_service.py      门面：保留现有公共函数名，转调上面的模块
```

## 拆分原则

1. **先加后减**：新模块上线时，`inst_service` 用 `from .x import *` 或显式导入保持旧名字可用，
   路由与测试不用改；确认无引用后再删旧定义。
2. **只做平移，不改逻辑**：每一步都是纯搬移 + 导入，行为不变，用全量 pytest 兜底。
3. **依赖方向**：`common ← stages ← 各 domain service ← inst_service(门面) ← routers`；
   领域模块之间不互相导入，共享数据访问走 `repo.py`。
4. **一次一域**：一个 PR 只拆一个领域，便于 review 和回滚。

## 进度

| 步骤 | 状态 | 说明 |
|---|---|---|
| ① `common.py` + `stages.py` | ✅ 已完成 | 抽出 81 + 184 行纯工具与状态机，`inst_service` 保留同名导入 |
| ② `guards.py` + `company_service.py` | ✅ 已完成 | 审计/成员/角色守卫 66 行；公司池（ensure_and_seed、seed/sync_company_universe、list/update/search、`_mapped_industry`）304 行。`get_company` 依赖研究域的 `list_cases`，留到 research 拆分后再迁 |
| ③ `research_service.py` | ⬜ | 立项、`_build_research`、六维生成、定稿门禁、版本锁定（约 1,500 行） |
| ④ `proposal_service.py` | ⬜ | 议案与三关审批（约 1,200 行） |
| ⑤ `execution_service.py` | ⬜ | 授权、执行、对账（约 900 行） |
| ⑥ `portfolio_service.py` | ⬜ | 持仓、论点、退出（约 700 行） |
| ⑦ `ai_service.py` | ⬜ | AI 备忘/对话/角色（约 1,000 行） |
| ⑧ 删除 `inst_service` 中的旧定义 | ⬜ | 只在确认没有外部引用后做 |

## 验证方式

每一步：`pytest tests/test_inst_*.py tests/test_inst_workflow_e2e.py` → 全量 `pytest tests` →
机构端 E2E（`scripts/ci/e2e.sh full inst`）。

## 风险

- 模块级常量与循环导入：领域模块只依赖 `common/stages/repo`，不反向依赖 `inst_service`；
- 若个别函数互相调用，先下沉到 `repo.py` 或 `common.py`，不要在领域模块之间直接 import。
