# SVQuant R5 KnowledgeHub修复回归报告

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 项目 | SVQuant |
| 阶段 | R5 Fix Cycle - KnowledgeHub Ask 链路修复与回归 |
| 日期 | 2026-09-24 |
| Git 分支 | master |
| Git 提交 | da1161e |
| 执行环境 | Windows 10 / Python 3.12.9 / Node.js v24.18.0 / PostgreSQL 16.15 |
| 后端地址 | `http://127.0.0.1:8766` |
| 主前端地址 | `http://127.0.0.1:9540` |
| KnowledgeHub 前端地址 | `http://127.0.0.1:9541` |
| R5 Fix Run ID | `R5_KH_FIX_1790270017` |
| 本轮结论 | BUG-R5-001 FIXED / Release Blocker 已解除 |

本报告仅记录 `BUG-R5-001` 的修复与回归，不覆盖原始 `R5-E2E与全量回归测试报告.md`，也不处理 R4 性能正式回归遗留项。

## 2. BUG-R5-001描述

| 项目 | 内容 |
| --- | --- |
| Bug ID | BUG-R5-001 |
| 严重程度 | Major |
| 模块 | KnowledgeHub |
| 失败接口 | `POST /api/kh/ask` |
| 原始现象 | R5 E2E 中 Ask 问答流程返回 HTTP 400，期望 HTTP 200 |
| 影响 | Collection 创建、Document 上传、Document 解析、Search 均通过，但问答链路无法闭环 |

原始失败证据来自 `docs/测试报告/R5-E2E与全量回归测试报告.md`：`KH ask 返回可判定答案（无 LLM 依赖口径）` 失败，实际 `POST /api/kh/ask` 返回 HTTP 400。

## 3. 根因分析

`/api/kh/ask` 的实现路径为：

1. `backend/app/routers/kh.py` catch-all 转发到 KnowledgeHub handler。
2. `KnowledgeHub/backend/knowledge_hub/http_handlers.py` 解析 `query`、`collectionIds`、`topK`。
3. `KnowledgeHub/backend/knowledge_hub/store.py::ask` 执行检索并生成回答。

根因是 Ask 在检索命中后强制要求默认 LLM 已配置：

| 问题 | 影响 |
| --- | --- |
| 有命中但未配置默认 LLM 时抛出 `KhLlmError` | R5 “无 LLM 依赖口径”无法通过 |
| HTTP 层将 `KhLlmError` 映射为 400 | Provider/LLM 外部服务问题被误归类为参数错误 |
| 不存在的 `collectionIds` 未在 Ask 前明确校验 | 非法集合容易被混淆为无命中或其他业务空态 |

因此，BUG-R5-001 不是前端字段漂移，也不是权限问题；请求体结构 `{ query, collectionIds, topK }` 与后端接收字段一致。

## 4. 修改文件

| 文件 | 修改内容 |
| --- | --- |
| `KnowledgeHub/backend/knowledge_hub/store.py` | 增加 Ask 无 LLM 降级答案；增加 collection 存在性校验 |
| `KnowledgeHub/backend/knowledge_hub/http_handlers.py` | 将 LLM 调用类错误映射为 HTTP 502，并为 KeyError 返回明确 404 |
| `KnowledgeHub/backend/knowledge_hub/llm.py` | 将底层 LLM 请求异常统一包装为 `KhLlmError` |
| `backend/tests/r5_kh_ask_regression.py` | 新增 `TC-KH-ASK-REGRESSION` 自动化回归脚本 |

## 5. 修复方案

### 5.1 无 LLM 配置场景

当检索命中但未配置默认 LLM 时，Ask 不再返回 400，而是返回基于检索片段的摘录式答案：

| 字段 | 行为 |
| --- | --- |
| HTTP Status | 200 |
| `answer` | 基于命中片段生成的可审计摘录 |
| `hits` | 保留检索命中 |
| `referencedDocuments` | 保留引用来源 |
| `llmConfigured` | `false` |
| `degraded` | `true` |
| `degradeReason` | `llm_not_configured` |

该方案不调用外部 LLM，不降低 Ask 接口的检索与引用要求，也不把失败测试改为通过。

### 5.2 参数与业务错误分类

| 场景 | 修复后状态 |
| --- | --- |
| 空问题 | HTTP 400 |
| 非法 collection | HTTP 404 |
| 普通用户访问 KH Ask | HTTP 403 |
| 匿名访问 KH | HTTP 401 |
| LLM Provider 异常 | HTTP 502 + `code=llm_unavailable` |

## 6. Ask回归测试结果

执行命令：

```powershell
python backend\tests\r5_kh_ask_regression.py
```

结果文件：

`backend/tests/R5_KH_FIX_1790270017_kh_ask_regression_results.json`

| Case ID | 测试项 | 结果 | 实际状态 |
| --- | --- | --- | --- |
| TC-KH-ASK-REGRESSION-001 | 合法用户 Ask 成功（无 LLM 降级答案） | PASS | HTTP 200 |
| TC-KH-ASK-REGRESSION-002 | 无权限用户 Ask 失败 | PASS | HTTP 403 |
| TC-KH-ASK-REGRESSION-003 | 非法 Collection 返回 404 | PASS | HTTP 404 |
| TC-KH-ASK-REGRESSION-004 | 空问题返回 400 | PASS | HTTP 400 |
| TC-KH-ASK-REGRESSION-005 | LLM 异常返回明确错误且不 500 | PASS | HTTP 502 |

## 7. KnowledgeHub E2E结果

执行命令：

```powershell
npm.cmd exec -- playwright test --config tests\e2e\playwright.config.ts e2e-04-kh.spec.ts
```

| 用例 | 结果 |
| --- | --- |
| KH 管理员登录（UI，:9531） | PASS |
| 创建知识库集合（UI）并落库 | PASS |
| 上传并摄取文档（UI setInputFiles → 自动 ingest） | PASS |
| 检索命中测试关键词（API，含向量摄取依赖） | PASS |
| KH ask 返回可判定答案（无 LLM 依赖口径） | PASS |
| KH 权限：普通用户 403、匿名 401 | PASS |
| 删除知识库集合（UI）并确认清理 | PASS |

清理结果：`backend/tests/r5_e2e_cleanup.py` 返回 PASS，`R5_TEST_*` 残留为 0。

## 8. 回归统计

| 指标 | 数量 |
| --- | ---: |
| 新增 Ask 回归用例 | 5 |
| KH E2E 用例 | 7 |
| 本轮执行总数 | 12 |
| PASS | 12 |
| FAIL | 0 |
| BLOCKED | 0 |

## 9. 缺陷状态

| Bug | 修复状态 | 回归状态 | 发布阻断 |
| --- | --- | --- | --- |
| BUG-R5-001 | FIXED | PASS | 已解除 |

## 10. 遗留风险

| 风险 | 状态 | 说明 |
| --- | --- | --- |
| R4 性能正式回归未执行 | OPEN | 用户已要求后续处理，本轮不进入 R4 性能回归 |
| LLM 真实回答质量 | OPEN | 本轮验证 API 集成、降级答案与错误分类，不评估真实 LLM 生成质量 |

## 11. R5状态建议

`BUG-R5-001` 已修复并通过回归，KnowledgeHub 主流程已恢复闭环：

创建 Collection → 上传 Document → 摄取 → Search → Ask → 删除 Collection。

就 R5 发布阻断项而言，当前可以进入 FINAL 测试报告汇总。FINAL 报告中仍需显式记录 R4 性能正式回归未执行这一独立遗留风险。
