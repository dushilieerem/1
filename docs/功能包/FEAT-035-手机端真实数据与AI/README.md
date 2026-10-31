# FEAT-035 手机端真实数据与 AI

| 项 | 内容 |
|---|---|
| 状态 | 首版可运行（PG→SQLite 缓存 + AI 面板） |
| 日期 | 2026-10-30 |
| 前置 | `10.29手机端朱梦研` 需求包、[数据接入与库表设计](../../数据设计/机构端与手机端-数据接入与库表设计-v0.1.md) |
| 代码 | `scripts/sync_invest_sqlite.py`、`invest-api/ai_endpoints.py`、`frontend/invest/src/components/AiPanel.tsx` |

## 1. 目标与范围

把 Invest H5 从 29 只演示标的升级为「PG 汇总 + SQLite 读取缓存」，并接入合规约束下的 AI 解读。

**做**：

- PG 服务层 → SQLite 缓存同步：全市场证券主表、选中池日线/估值/财务、指数、公告/研报/要闻。
- 修复 `invest-api` 硬编码数据日期与写入时间。
- AI 接口：意图路由、日报、个股、组合、公告、条件解析；前置红线 + 后置扫描。
- H5 面板：个股「AI 解读」、首页「AI 今日解读」、组合「AI 组合诊断」。

**不做**：实时行情、分时、推送、社区/UGC、ETF 穿透、问 AI 语音/OCR、量化模式（本轮）。

## 2. 架构

```text
marketdata parquet ──etl_marketdata.py──▶ PostgreSQL（ref_/md_/fin_/doc_）
                                              │
                                              ├─ 机构端直接读 PG
                                              └─ sync_invest_sqlite.py ──▶ invest-api SQLite
                                                                              │
                                                                      Invest H5（9540）
                                                                              │
                                                                      /api/invest/ai/* ──▶ backend/ai/router
```

- PG 是汇总层；SQLite 是可重建读取缓存。
- 用户数据（watchlist/portfolio/risk/events/audit）不同步覆盖。
- 账号仍复用主站 `/api/auth/*`。

## 3. 同步与数据

| 表 | 来源 | 规模/口径 |
|---|---|---|
| `stocks` | `ref_security` + 最新 `md_daily_bar`/`md_valuation_daily` | 全 A 股 5,956；价格未复权，市值亿元 |
| `bars` | `md_daily_bar`，优先未复权，缺失回退后复权 | 默认 500 只 × 750 日 |
| `valuations` | `md_valuation_daily` | 同池 × 750 日 |
| `financials` | `fin_income_statement` + `fin_cash_flow` + `fin_indicator` | 5 只已采集；收入/净利亿元，比率百分数 |
| `indices` | `md_index_bar` | 000300 / 000905 |
| `news` | `doc_item` | 最近 300 条，标题+链接 |

运行：

```bash
/home/dev01/program/anaconda3/bin/python scripts/sync_invest_sqlite.py
# 指定库与池大小
/home/dev01/program/anaconda3/bin/python scripts/sync_invest_sqlite.py --db invest-api/data/invest.dev.db --limit-symbols 800
```

## 4. AI 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/invest/ai/status` | 各 TaskSpec 是否可用 |
| POST | `/api/invest/ai/intent` | 意图 + 槽位 |
| POST | `/api/invest/ai/chat` | 路由后调用对应 Worker |
| POST | `/api/invest/ai/stock/{code}` | 个股解读 |
| POST | `/api/invest/ai/daily` | 日报/复盘 |
| POST | `/api/invest/ai/portfolio` | 组合诊断 |
| POST | `/api/invest/ai/announcement` | 公告要点 |
| POST | `/api/invest/ai/condition` | 条件解析 |

合规：

- 前置命中「买入/卖出/目标价/保证收益/自动交易…」→ 固定话术，不进模型。
- 后置扫描「建议买入/建议卖出/目标价/保证收益…」→ 替换固定话术。
- AI 输出必须带 `disclaimer` 与 `meta.dataSource`；无 Key 返回 503，不用 mock 伪装。

## 5. 验证

| 项 | 结果 |
|---|---|
| `invest-api` 导入与 AI 路由注册 | 通过（OpenAPI 8 条 AI 路径） |
| `invest-api` pytest | 6 passed（smoke + 登录代理 + AI 合规 4 条） |
| 前端 `tsc` | 通过；仅剩 `KLineChart/main.tsx` 两条既有错误 |
| 真实模型调用 | `invest.intent` / `invest.stock` 通过；`inst.debate` 通过 |
| 数据质量接口 | `ok=true`；日线 503/5579、估值池内 500/500、财务 5/500（warn）、ETF 排除 |
| 浏览器走查 | **未做** |

## 6. 已知缺口

- 全市场日线未全部写入 SQLite（默认 500 只池）；搜索可命中全市场，但无池外 K 线。
- 主题/热点仍是原种子数据；未用真实行业指数重算。
- 公告/研报只有标题与链接；AI 公告解读需要传入正文摘要，当前前端未接。
- 条件选股只做「解析」，未执行筛选；下一步接 SQL 筛选与结果卡。
- SQLite 缓存重建期间用户请求可能读到空表；生产应加原子切换或双库。
- 未做真机、弱网、CSP/限流/WAF 与公开 Gate。

## 7. 下一步

1. 等 `md_daily_bar` 未复权同步完成，跑一次全量 `sync_invest_sqlite.py` 并核验 5 只样本。
2. 条件选股接筛选执行；公告解读接 `doc_item` 摘要。
3. 主题/热点用真实行业指数与成分重算。
4. 把 `rules.py` 读模型逐步迁到 PG repository，SQLite 只保留离线缓存。
5. 真机与 E2E；公开 Gate 仍按 `PUBLIC_LAUNCH.md` 执行。
