# SVQuant R5 E2E与全量回归测试报告

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 项目 | SVQuant |
| 阶段 | R5 E2E 与全量回归测试 |
| 执行日期 | 2026-09-24 |
| Git 分支 | master |
| Git 提交 | da1161e |
| 执行环境 | Windows 10 / Python 3.12.9 / Node.js v24.18.0 / PostgreSQL 16.15 |
| 后端地址 | `http://127.0.0.1:8766` |
| 主前端地址 | `http://127.0.0.1:9540` |
| KnowledgeHub 前端地址 | `http://127.0.0.1:9541` |
| R5 Run ID | `R5_TEST_1790268979` |
| 最终结论 | NOT READY FOR RELEASE |

说明：用户已明确要求进入 R5，R4 性能正式回归未完成的问题本轮按“已接受遗留风险”记录，不作为 R5 自动化执行阻断。

## 2. 执行范围

| 范围 | 执行状态 | 说明 |
| --- | --- | --- |
| 普通用户流程 | 已执行 | 注册、登录、退出、行情、自选股、社区 |
| 研究员流程 | 已执行 | 因子库、自定义因子、因子面板、策略研究、策略运行 |
| KnowledgeHub 流程 | 部分通过 | 登录、集合创建、上传、检索通过；ask 失败 |
| AI 与 Agent 流程 | 已执行 | AI 页面、模型列表、匿名拒绝、错误路径、Agent quota、非法 skills |
| 管理员流程 | 已执行 | 审计日志、KH 管理、社区举报处理 |
| 安全关键回归 | 已执行 | RBAC、IDOR、匿名访问、XSS 浏览器渲染断言 |
| R4 性能修复回归 | 未执行 | 用户要求后续再处理，作为遗留风险 |

## 3. 自动化结果

执行命令：

```powershell
npm.cmd exec -- playwright test --config tests\e2e\playwright.config.ts
```

| 指标 | 数量 |
| --- | ---: |
| 自动化用例总数 | 38 |
| PASS | 36 |
| FAIL | 1 |
| SKIPPED | 1 |
| 执行时长 | 约 2.0 分钟 |
| 清理结果 | PASS，`R5_TEST_*` 残留为 0 |

证据：

| 项目 | 路径 |
| --- | --- |
| Playwright JSON | `tests/e2e/test-results/r5-e2e-results.json` |
| 失败 trace | `tests/e2e/test-results/artifacts/e2e-04-kh-KH-ask-返回可判定答案（无-LLM-依赖口径）/trace.zip` |

## 4. 分模块结果

| 模块 | 结果 | 说明 |
| --- | --- | --- |
| 认证与会话 | PASS | 注册、登录失败提示、成功登录、退出登录、受保护路由跳转均通过 |
| 行情与自选股 | PASS | 行情接口、创建自选组合、加入标的、跨用户访问拒绝通过 |
| 因子研究 | PASS | 因子库、自定义因子、非法输入、RE 因子目录、因子面板通过 |
| 策略研究 | PASS | 列表、项目配置、内置策略库、Run 保存与报告页、策略广场权限通过 |
| KnowledgeHub | FAIL | 集合创建、上传、检索、权限通过；`POST /api/kh/ask` 返回 400 |
| AI 与 Agent | PASS | 模型列表、匿名拒绝、无效模型错误路径、Agent quota、非法 skills 通过 |
| 社区与管理 | PASS | 发帖、评论、点赞、收藏、举报、审核、IDOR、XSS、审计日志通过 |

## 5. 失败项

| 编号 | 严重程度 | 模块 | 失败项 | 实际结果 | 状态 |
| --- | --- | --- | --- | --- | --- |
| BUG-R5-001 | Major | KnowledgeHub | KH ask 返回可判定答案 | `POST /api/kh/ask` 返回 HTTP 400，期望 200 | OPEN |

影响：KnowledgeHub 文档上传与检索链路已经通过，但问答链路未达到 R5 准出要求。由于该功能属于端到端用户主流程，当前不建议发布。

## 6. 跳过项

| 用例 | 原因 |
| --- | --- |
| 删除知识库集合（UI）并确认清理 | 依赖 `KH ask` 所在 spec 前置链路；最终清理脚本已兜底删除测试集合 |

## 7. 已修正的测试执行问题

本轮为使 R5 能真实覆盖产品链路，修正了 E2E 脚本中的测试夹具与选择器漂移：

| 范围 | 修正内容 |
| --- | --- |
| 认证夹具 | 已存在测试账号时复用登录，避免重复注册中断 |
| 主前端登录 | 避免把用户名填入导航搜索框，改为定位认证表单 |
| 自选股 | 显式切换到浏览选股后执行标的加入 |
| KH | 对齐创建集合、上传保存、文档列表 API 路由 |
| Agent quota | 对齐当前后端契约：管理员 `GET /api/agent/usage`、`POST /api/agent/usage/quota` |
| 社区发帖 | 对齐富文本编辑器 `contenteditable` 输入 |
| 清理脚本 | 兼容 dict 游标并确认残留为 0 |

这些修正不降低业务断言，只修复测试脚本与当前 UI/API 契约不一致的问题。

## 8. 遗留风险

| 风险 | 等级 | 说明 |
| --- | --- | --- |
| RISK-R5-001 | High | R4 性能修复正式回归未执行，用户要求后续处理 |
| RISK-R5-002 | Medium | Vite 日志提示 Tiptap extension `link`、`underline` 重复注册，当前未导致 R5 失败 |
| RISK-R5-003 | Medium | Browser 插件不可用，本轮使用项目 Playwright 执行浏览器自动化 |

## 9. 发布判定

R5 最终结论：`NOT READY FOR RELEASE`

不满足发布准出的原因：

1. 存在 1 个 R5 Major 缺陷：`BUG-R5-001`。
2. KnowledgeHub ask 端到端问答链路失败。
3. R4 性能正式回归仍是遗留风险，尚未形成发布前完整性能证据。

建议下一步仅处理 `BUG-R5-001`，完成 KH ask 修复与 R5 回归；随后再补做 R4 性能正式回归。
