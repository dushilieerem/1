# SVQuant最终测试报告

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 项目 | SVQuant |
| 版本 | 当前测试版本，Git `da1161e` |
| 测试周期 | 2026-09-23 至 2026-09-24 |
| 环境 | Windows 10 / Python 3.12.9 / Node.js v24.18.0 / PostgreSQL 16.15 |
| 测试负责人 | Codex |
| 报告类型 | FINAL 最终测试总结与发布质量评审 |
| 最终结论 | CONDITIONALLY READY FOR RELEASE |

本报告基于 `docs/测试设计/` 与 `docs/测试报告/` 中 R0-R5 已有测试结果汇总生成，不重新设计测试体系，不覆盖历史报告，不删除失败记录。

## 2. 项目测试背景

SVQuant 本轮测试围绕已实现的 V0 能力展开，覆盖认证与权限、行情与自选股、因子研究、策略研究、ResearchEngine 网关、KnowledgeHub、AI/Agent、社区、新闻、管理员审计、数据库、安全、性能与前端 E2E。

测试设计基线来自 `docs/测试设计/README.md`、`01-测试策略.md`、`02-测试计划.md` 与 `08-需求测试追踪矩阵.md`。测试设计声明正式测试用例为 308 条，另有 6 条 E2E 核心链路。RTM 中功能需求行合计 56 行，基于测试用例设计层面的覆盖状态为已覆盖，另有记录型 GAP 与 NOT APPLICABLE 项。

## 3. 测试体系概览

| 资产 | 状态 |
| --- | --- |
| 测试策略 | 已建立，按 L1-L9 分层和 P0/P1/P2/P3 风险驱动 |
| 测试计划 | 已建立，定义 R0-R5 轮次、准入准出、账号与证据规范 |
| 测试用例 | 308 条 TC 用例 + 6 条 E2E 链路 |
| RTM | 56 行功能需求映射，设计层覆盖完整 |
| 自动化脚本 | 已形成 R1、R2、R3、R4、R5 自动化脚本与结果文件 |
| 测试报告 | R0-R5 与修复回归报告已形成 |

## 4. R0-R5执行总结

| 阶段 | 类型 | 状态 | 主要结论 |
| --- | --- | --- | --- |
| R0 | 测试准备 | READY | 环境、构建、数据库、RE、契约脚本、KH smoke 均具备进入 R1 条件 |
| R1 | 功能权限 | READY FOR R2 | P0 核心功能与权限 55/55 PASS；KH 匿名读写 Critical 缺陷已修复 |
| R2 | 集成 | READY FOR R3 | P1 自动化执行子集 101/101 PASS；不代表 308 全量用例通过 |
| R3 | 安全 | READY FOR R4 | 原始 R3 发现 JWT Critical 与依赖 High；修复回归后 64/64 PASS，缺陷关闭 |
| R4 | 性能 | NOT READY / ACCEPTED RISK | 性能基线发现 4 个性能缺陷；已优化但正式完整回归未执行 |
| R5 | E2E | Release Blocker 已解除 | 原始 R5 36 PASS/1 FAIL/1 SKIPPED；KH Ask 修复后新增 12/12 PASS |
| FINAL | 发布评审 | CONDITIONALLY READY FOR RELEASE | 无开放 Blocker/Critical；核心业务、安全关键项与关键 E2E 通过；R4 性能正式回归缺口作为发布条件风险 |

## 5. 测试覆盖范围

| 模块 | 覆盖状态 |
| --- | --- |
| 认证 | R0/R1/R3/R4/R5 已覆盖登录、JWT、会话、匿名拒绝、并发基线 |
| 用户 | R1/R2/R5 已覆盖注册、资料、关注、禁用用户、权限边界 |
| 行情 | R0/R1/R2/R4/R5 已覆盖 symbols、指数、日线异常与稳定性基线 |
| 因子 | R1/R2/R5 已覆盖因子库、自定义因子、RE catalog、隔离 |
| 策略 | R1/R2/R4/R5 已覆盖项目、Run、用户库、策略广场、并发查询 |
| KnowledgeHub | R0/R1/R2/R3/R5 已覆盖权限、集合、文档、上传、摄取、搜索、Ask、删除 |
| AI | R2/R3/R5 已覆盖 API 集成、参数校验、错误路径、提示注入基础探测 |
| 社区 | R2/R3/R5 已覆盖发帖、评论、点赞、收藏、举报、审核、XSS 风险 |
| 新闻 | R2 已覆盖列表、字典、非法 ID、来源校验 |
| 管理员 | R1/R2/R3/R5 已覆盖审计查询、权限拒绝、日志脱敏 |
| 数据库 | R0/R1/R2/R4 已覆盖连接、40 表存在、数据生命周期、查询基线 |
| 安全 | R1/R3/R3 修复回归/R5 已覆盖 JWT、RBAC、IDOR、SQL 注入、上传、敏感信息 |
| 性能 | R4 已执行基线与优化尝试；正式完整回归未完成 |
| 前端 | R0/R2/R3/R5 已覆盖构建验证与关键 E2E，非完整视觉/可访问性回归 |

## 6. 自动化测试统计

| 类型 | 脚本/资产 | 自动化 Case 或检查点 |
| --- | --- | ---: |
| R0 readiness 与 smoke | contract、KH smoke、构建与健康检查 | 34 |
| R1 P0 API 套件 | `backend/tests/r1_p0_api_suite.py` | 55 |
| R2 P1 集成套件 | `backend/tests/r2_p1_integration_suite.py` | 101 |
| R3 安全套件 | `backend/tests/r3_security_suite.py` | 54 |
| R3 修复回归 | `backend/tests/r3_jwt_regression.py` + R3 安全回归 + audit/build | 64 |
| R4 性能基线 | `backend/tests/performance/performance_baseline.py` | 66398 请求 |
| R4 优化目标回归 | `backend/tests/performance/r4_fix_regression.py` | 7（4 目标性能场景 + 1 编译检查 + 2 短冒烟） |
| R5 E2E | Playwright `tests/e2e/` | 38 |
| R5 KH Ask 回归 | `backend/tests/r5_kh_ask_regression.py` + KH E2E 单模块 | 12 |

按 Case/检查点口径汇总，不把 R4 性能请求数混入普通用例数：

| 指标 | 数量 |
| --- | ---: |
| 计划测试数 | 308 TC + 6 E2E |
| 已执行 Case/检查点数 | 365 |
| PASS | 357 |
| FAIL | 7 |
| BLOCKED | 0 |
| SKIPPED | 1 |
| R4 性能请求总数 | 66398 |
| R4 性能失败请求数 | 3350 |

说明：失败项包含历史失败与修复前失败，不代表最终仍全部开放。最终开放状态见缺陷统计与风险评估。

口径核对（365 可复算）：34 + 55 + 101 + 54 + 64 + 38 + 12 + 7 = 365。

FAIL 7 的构成：R3 安全套件 3（`TC-SEC-009`、`TC-SEC-010B`、`TC-SEC-026`）+ R4 第一次目标回归 3（`PERF-R4-001/002/004`）+ R5 原始 E2E 1（`BUG-R5-001`）；SKIPPED 1 为 R5 原始 E2E。R0 的 34 项按修复后复测通过口径计入，其修复前失败（`BUG-R0-001/002`）不计入 FAIL 统计。

## 7. 功能质量总结

R1 与 R2 显示核心后端能力具备较好的可测性和可回归性：认证、权限、因子、策略、行情、自选股、社区、新闻、管理审计与 KnowledgeHub 的主要 API 链路均有自动化覆盖。

R5 E2E 覆盖普通用户、研究员、AI/Agent、管理员和 KnowledgeHub 关键流程。原始 R5 中 KnowledgeHub Ask 是唯一发布阻断；修复后 KH 主流程已经闭环：创建 Collection、上传 Document、摄取、Search、Ask、删除均通过。

功能侧仍需注意：R2/R5 结论均不是 308 条全量手工/自动化用例全部通过；它们代表对应阶段的自动化执行子集和关键 E2E 链路通过。

## 8. 安全质量总结

| 安全项 | 最终状态 | 说明 |
| --- | --- | --- |
| 认证绕过 | 未发现开放阻断 | R1 修复 KH 匿名 admin；R3 验证 DEV_SKIP_AUTH 当前关闭 |
| JWT 问题 | 已修复 | 默认 JWT Secret 伪造管理员 Token 的 Critical 缺陷已 CLOSED |
| IDOR | 未发现严重 IDOR | Watchlist、策略、因子、KH 集合文档等均通过隔离验证 |
| SQL Injection | 未发现 | 社区、新闻、策略广场、管理日志过滤 payload 未导致异常或泄露 |
| XSS | 非阻断风险 | R3 API 层发现社区可保存 HTML/JS 文本，R5 浏览器渲染断言通过；仍建议专项覆盖更多展示点 |
| Secret 泄露 | 未发现报告泄露 | `.env` 未被 Git 跟踪，审计响应和报告未记录可复用密钥 |
| 权限模型 | 关键回归通过 | RBAC、admin-only、匿名拒绝、普通用户拒绝均通过关键回归 |
| 依赖安全 | 已修复 | R3 修复后 `npm audit --audit-level=high` high=0、critical=0 |

R3 原始状态为 `NOT READY FOR R4`，修复回归后变更为 `READY FOR R4`。遗留安全风险为登录失败限流、CORS wildcard、安全响应头与 XSS 展示点专项验证，均未登记为开放 Critical/Blocker。

## 9. 性能质量总结

R4 已执行 API 延迟、并发、业务并发、数据库性能、外部依赖、30 分钟稳定性与 Build Verification。单接口低压力下核心 API 100 次请求均 0% 错误率；数据库查询基线在当前小数据规模下未发现慢查询、连接泄漏或长事务。

但 R4 同时发现明确性能缺陷：

| 范围 | 基线问题 | 当前状态 |
| --- | --- | --- |
| `/api/auth/me` | 100 并发错误率 5.27%，P95 14206.76 ms | 已优化，正式回归未执行 |
| `/api/strategy/runs` | 20 并发错误率 4.28% | 已优化，正式回归未执行 |
| `/api/re/health` | 15 秒超时 | 目标回归已通过，仍建议纳入正式回归 |
| `/api/market-data/symbols` | 30 分钟错误率 11.49%，P95 15010.30 ms | 已优化，正式回归未执行 |

R4 性能优化报告结论仍为 `NOT READY FOR R5`，原因是二次优化后的正式完整回归未执行。用户后续要求进入 R5，因此 FINAL 只能将其记为已接受但未关闭的发布条件风险，不能声明系统性能优秀或生产容量已验证。

## 10. E2E质量总结

R5 原始 E2E 共 38 条，结果为 36 PASS、1 FAIL、1 SKIPPED。失败项为 `BUG-R5-001`：`POST /api/kh/ask` 返回 400。修复回归后：

| 范围 | 结果 |
| --- | --- |
| 新增 KH Ask 回归 | 5/5 PASS |
| KH E2E 单模块 | 7/7 PASS |
| Release Blocker（`BUG-R5-001`，严重度 Major，按发布阻断影响处理） | 已解除 |

R5 覆盖用户流程、研究流程、KnowledgeHub、AI/Agent 与管理员流程。当前关键 E2E 链路可进入 FINAL 汇总，但 R4 性能正式回归仍是单独风险。

## 11. 缺陷统计

| 分类 | 数量 |
| --- | ---: |
| 历史登记 Bug/Perf 缺陷 | 11 |
| 已关闭/已解决 | 7 |
| 已修复但回归待完成 | 3 |
| 已部分回归通过但建议纳入正式回归 | 1 |
| 开放 Blocker | 0 |
| 开放 Critical | 0 |

最终缺陷列表：

| 编号 | 阶段 | 等级 | 描述 | 状态 |
| --- | --- | --- | --- | --- |
| BUG-R0-001 | R0 | Major | KH smoke `/api/kh/ask` 预期漂移 | RESOLVED |
| BUG-R0-002 | R0 | Major | 契约测试账号夹具缺失 | RESOLVED |
| BUG-R1-004 | R1 | Critical | 匿名用户可查询 KH Collections | RESOLVED |
| BUG-R1-005 | R1 | Critical | 匿名用户可创建 KH Collection | RESOLVED |
| BUG-R3-001 | R3 | Critical | 默认 JWT 密钥可伪造管理员 Token | CLOSED |
| BUG-R3-002 | R3 | High | 前端依赖存在 high/critical 漏洞项 | CLOSED |
| PERF-R4-001 | R4 | High | `/api/auth/me` 高并发超时/失败 | FIXED / REGRESSION PENDING |
| PERF-R4-002 | R4 | Major | `strategy run` 查询并发失败 | FIXED / REGRESSION PENDING |
| PERF-R4-003 | R4 | Major | RE health timeout | FIXED / PARTIAL REGRESSION PASS |
| PERF-R4-004 | R4 | High | `market-data/symbols` 稳定性失败 | FIXED / REGRESSION PENDING |
| BUG-R5-001 | R5 | Major | KH Ask 返回 400，问答流程无法闭环 | FIXED / PASS |

按等级汇总：

| 等级 | 历史数量 | 最终开放数量 |
| --- | ---: | ---: |
| Blocker | 0 | 0 |
| Critical | 3 | 0 |
| High | 3 | 2 |
| Major | 5 | 2 |

说明：`Blocker/Critical` 等级指缺陷严重度评级。第 4、10 节所称 `Release Blocker` 指发布阻断影响，而非缺陷严重度等级：`BUG-R5-001` 严重度评级为 Major，但因 KnowledgeHub Ask 属核心 E2E 链路、失败即导致问答主流程无法闭环，被判定为发布阻断项。等级汇总中的 Blocker 数量按严重度评级口径统计，因此“历史 Blocker = 0”与 R5 曾存在发布阻断并不矛盾。
| Medium | 0 | 0 |
| Low | 0 | 0 |

## 12. 风险评估

| 风险 | 等级 | 状态 | 建议 |
| --- | --- | --- | --- |
| R4 性能正式回归未完成 | High | 遗留 / 发布条件风险 | 发布前补跑 `r4_fix_regression.py` 并更新结论 |
| `/api/auth/me`、`strategy/runs`、`market-data/symbols` 性能修复未正式闭环 | High | 遗留 | 完成同等并发、同等时长回归后再关闭 |
| 登录失败未观察到限流或锁定 | Medium | 遗留 | 增加登录限流、账户锁定或 IP 节流策略 |
| XSS 展示点专项不足 | Medium | 遗留 | 对社区、Markdown、富文本展示点补充浏览器安全回归 |
| CORS wildcard | Low | 遗留 | 生产环境改为白名单 |
| 缺少常见安全响应头 | Low | 遗留 | 增加安全响应头基线 |
| LLM 真实回答质量未验证 | Medium | 已接受风险 | 后续单独做 LLM 质量与对抗评测 |
| 大数据量/生产容量未验证 | Medium | 已接受风险 | 构造大规模数据集后重新测性能 |
| CPU/内存时间序列未采集 | Medium | 已接受风险 | 安装 `psutil` 或接入监控后补采 |
| Browser 插件不可用，使用 Playwright 替代 | Medium | 已接受风险 | 后续可增加截图与可访问性证据 |

阻断风险：当前无开放 Blocker/Critical；R4 性能回归缺口是发布条件风险，不应在没有补测的情况下声明完全 READY。

非阻断风险：R3 Medium/Low 安全建议、LLM 质量验证、前端完整视觉/可访问性、生产容量评估。

## 13. 需求覆盖分析

RTM 中功能 REQ 行合计 56 行，设计层面除登记型 GAP/待确认项外均已覆盖。覆盖率口径为“已有测试 Case 覆盖”，不是“全部已执行通过”。

| 需求范围 | 覆盖状态 |
| --- | --- |
| 用户与权限 | 已覆盖，登录限流为记录型 GAP |
| 因子研究 | 已覆盖 |
| 策略研究 | 已覆盖 |
| 行情与自选股 | 已覆盖 |
| 社区 | 已覆盖 |
| 新闻 | 已覆盖 |
| KnowledgeHub | 已覆盖，KH Ask 已修复回归 |
| AI 与 Agent | 已覆盖，真实 LLM 质量未验证 |
| 管理与审计 | 已覆盖 |
| ResearchEngine 网关 | 已覆盖 |
| 全局约束与 NFR | 已覆盖，性能达标结论待正式回归 |

设计覆盖率：100%（基于已有测试 Case 覆盖）。

执行覆盖说明：R1/R2/R3/R5 均为阶段性自动化子集与关键链路执行，不代表 308 条用例已经全部逐条执行并通过。

## 14. 测试资产清单

测试脚本：

| 资产 | 用途 |
| --- | --- |
| `backend/tests/r1_p0_api_suite.py` | R1 P0 核心功能与权限 |
| `backend/tests/r2_p1_integration_suite.py` | R2 P1 功能与集成 |
| `backend/tests/r3_security_suite.py` | R3 安全专项 |
| `backend/tests/r3_jwt_regression.py` | R3 JWT 修复回归 |
| `backend/tests/performance/performance_baseline.py` | R4 性能基线 |
| `backend/tests/performance/r4_fix_regression.py` | R4 性能优化回归 |
| `backend/tests/r5_kh_ask_regression.py` | R5 KH Ask 修复回归 |
| `backend/tests/r5_e2e_cleanup.py` | R5 测试数据清理 |
| `tests/e2e/` | R5 Playwright E2E |
| `backend/scripts/contract/run_all.py` | 契约测试基线 |
| `KnowledgeHub/backend/scripts/smoke_kh_api.py` | KH API 冒烟 |
| `KnowledgeHub/backend/scripts/smoke_structured.py` | KH 结构化 smoke |

测试报告：

| 报告 | 路径 |
| --- | --- |
| R0 测试就绪性执行报告 | `docs/测试报告/R0-测试就绪性执行报告.md` |
| R1 P0 核心功能与权限测试报告 | `docs/测试报告/R1-P0核心功能与权限测试报告.md` |
| R2 P1 功能与集成测试报告 | `docs/测试报告/R2-P1功能与集成测试报告.md` |
| R3 安全专项测试报告 | `docs/测试报告/R3-安全专项测试报告.md` |
| R3 安全修复与回归报告 | `docs/测试报告/R3-安全修复与回归报告.md` |
| R4 性能与稳定性基线测试报告 | `docs/测试报告/R4-性能与稳定性基线测试报告.md` |
| R4 性能优化与回归报告 | `docs/测试报告/R4-性能优化与回归报告.md` |
| R5 E2E 与全量回归测试报告 | `docs/测试报告/R5-E2E与全量回归测试报告.md` |
| R5 KnowledgeHub 修复回归报告 | `docs/测试报告/R5-KnowledgeHub修复回归报告.md` |
| FINAL 最终测试报告 | `docs/测试报告/FINAL-SVQuant最终测试报告.md` |

测试数据：

| 前缀 | 用途 | 状态 |
| --- | --- | --- |
| `R1_TEST_*` | R1 标准测试账号与临时业务数据 | 业务数据清理，标准账号保留 |
| `R2_TEST_*` | R2 集成测试数据 | 已清理 |
| `R3_TEST_*` | R3 安全测试数据 | 已清理 |
| `R4_PERF_TEST_*` | R4 性能测试数据 | 业务数据已清理，审计日志保留 |
| `R5_TEST_*` / `R5_KH_FIX_*` | R5 E2E 与 KH Ask 回归数据 | 已清理 |

## 15. 发布质量评估

READY 条件核对：

| 条件 | 状态 | 说明 |
| --- | --- | --- |
| Blocker = 0 | PASS | 未登记开放 Blocker |
| Critical = 0 | PASS | R1/R3 Critical 均已修复关闭 |
| 核心业务流程 PASS | PASS | R1/R2/R5 核心流程通过，KH Ask 已修复 |
| 安全关键项 PASS | PASS | JWT、RBAC、IDOR、SQL 注入、Secret 泄露关键项通过 |
| 关键 E2E PASS | PASS | R5 关键 E2E 阻断已解除 |
| 性能发布证据完整 | NOT PASS | R4 正式完整回归未执行，性能缺陷仍有回归待完成 |

综合判断：当前不应写 `READY FOR RELEASE`，因为 R4 性能正式回归尚未闭环；也不应写 `NOT READY FOR RELEASE`，因为开放发布阻断项已解除，且无开放 Blocker/Critical。最合适结论为 `CONDITIONALLY READY FOR RELEASE`。

## 16. 最终测试结论

SVQuant 当前达到有条件发布质量：

1. R0-R3 安全与核心功能链路已通过阶段性验证。
2. R3 原始 Critical/High 安全缺陷已修复并回归关闭。
3. R5 原始 KnowledgeHub Ask 发布阻断已修复并回归通过。
4. 关键 E2E 链路已经恢复闭环。

发布前建议至少完成以下条件：

1. 执行 R4 二次优化后的正式完整性能回归。
2. 若 R4 回归通过，将 `PERF-R4-001/002/004` 从 `REGRESSION PENDING` 调整为 CLOSED；`PERF-R4-003` 也须通过同一轮正式完整回归后，从 `FIXED / PARTIAL REGRESSION PASS` 调整为 CLOSED。
3. 在发布说明中记录 LLM 真实质量、大数据量容量、登录限流、安全响应头等非阻断风险。

最终结论：`CONDITIONALLY READY FOR RELEASE`。
