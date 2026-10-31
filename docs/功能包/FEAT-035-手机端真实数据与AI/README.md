# FEAT-035 手机端真实数据与 AI

| 项 | 内容 |
|---|---|
| 状态 | 首版可运行（PG 读模型 + AI 面板；SQLite 已下线） |
| 日期 | 2026-10-31 |
| 前置 | `10.29手机端朱梦研` 需求包、[数据接入与库表设计](../../数据设计/机构端与手机端-数据接入与库表设计-v0.1.md) |
| 代码 | `backend/services/invest/*`、`backend/app/routers/invest.py`、`backend/app/routers/invest_ai.py`、`frontend/invest` |

## 1. 目标与范围

把 Invest H5 从 29 只演示标的升级为「主后端 + PostgreSQL」：

- 账号、登录、注册、找回密码统一走主站 `/api/auth/*`；
- 手机端 `/api/invest/*` 并入主后端，不再运行独立 `invest-api`；
- 行情/估值/财务来自 PG 服务层；用户数据落 `invest_*` 表；
- AI 复用 `backend/ai/router`，合规红线不变。

**做**：

- `invest_stocks` 服务层快照：A 股 5,576 只 + 美股 16,273 只 + ETF；代码规则见 §3。
- `bars` / `valuations` / `financials` / `news` / `indices` 兼容视图，保持原读模型查询。
- AI 接口 8 个：意图、聊天、个股、日报、组合、公告、条件解析、状态。
- H5 面板：个股/首页/组合 AI 解读 + 搜索条件解析。

**不做**：实时行情、分时、推送、社区/UGC、ETF 穿透、语音/OCR、量化模式。

## 2. 架构

```text
marketdata parquet ──etl_marketdata.py / etl_us_marketdata.py──▶ PostgreSQL
                                                                    │
                                              ┌─────────────────────┴─────────────────────┐
                                              │ invest_stocks 快照 + bars/… 兼容视图        │
                                              │ invest_* 用户数据                          │
                                              └─────────────────────┬─────────────────────┘
                                                                    │
                                                    主后端 /api/invest/* + /api/invest/ai/*
                                                                    │
                                                        手机 H5（9541，与主后端同源）
```

- PG 是唯一存储；SQLite 已删除。
- `invest_stocks` 由 `scripts/refresh_invest_serving.py` 在 ETL 后重建；避免每次请求扫描 4,800 万行日线。
- 用户数据（自选/组合/风测/事件/审计）不被快照重建覆盖。

## 3. 数据与代码规则

| 项 | 规则 |
|---|---|
| A 股/ETF 代码 | 裸代码，如 `600519`、`510300` |
| 美股代码 | 全代码，如 `AAPL.O`；避免 `AAC.N` / `AAC.O` 等跨交易所重名 |
| 行情 | CN 后复权/未复权；US 后复权/bfq（`none`） |
| 估值 | A 股 `md_valuation_daily`；美股无估值源，页面标注「待补充」 |
| 财务 | 东财三表（5 只 A 股首版）；美股无财务，标注「待补充」 |
| 数据日 | `invest_meta.dataDate`，取 `md_daily_bar` 最新交易日 |

## 4. 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/invest/meta` | 数据日期/来源/是否演示 |
| GET | `/api/invest/data-quality` | 日线/财务/估值/ETF/新鲜度 |
| GET | `/api/invest/home` | 首页日报/复盘/指数/热点/自选（需登录） |
| GET | `/api/invest/topic/{id}` | 热点详情 |
| GET | `/api/invest/stock/{code}` | 个股行情/财务/估值/风险 |
| GET | `/api/invest/search?q=` | 全市场搜索 + 预设条件 |
| GET | `/api/invest/news?kind=` | 公告/研报/要闻 |
| GET/POST/DELETE | `/api/invest/watchlist` | 自选 |
| POST | `/api/invest/events` | 关注事件 |
| GET/POST | `/api/invest/risk-profile` | 风险测评 |
| GET | `/api/invest/portfolio` | 组合体检 |
| POST | `/api/invest/portfolio/import` | 导入持仓 |
| GET | `/api/invest/account/export` | 导出 |
| DELETE | `/api/invest/account/data` | 删除 Invest 数据 |
| GET | `/api/invest/ai/status` | AI 能力 |
| POST | `/api/invest/ai/intent` / `chat` / `stock/{code}` / `daily` / `portfolio` / `announcement` / `condition` | AI 能力 |

## 5. 验证

| 项 | 结果 |
|---|---|
| 主后端路由 | `/api/invest/*` + `/api/invest/ai/*` 均 200；demo 账号可登录 |
| 个股 600519 | 现价 1392.05、PE 21.37、PB 6.93、180 根 K 线、102 期财务 |
| 个股 AAPL.O | 现价 348.91、180 根 K 线；无估值/财务，页面标注待补充 |
| 数据质量 | `ok=true`；CN 2026-10-30 / US 2026-10-29；有日线 13,442 只（US 有价） |
| AI | `invest.stock`/`intent` 真实模型通过；越界请求固定话术 |
| 测试 | `backend/tests/test_invest_ai_compliance.py` 4 passed；机构 auth 9 passed |

## 6. 已知缺口

- 美股只有行情，无财务/估值/公告；研究页显示「待补充」。
- 主题/热点仍是种子数据；未用真实行业指数重算。
- 找回密码、邮箱验证、SSO token-exchange 尚未接主站。
- 手机 H5 已通过主站 `/m` 同域 iframe 嵌入，并用主站令牌 SSO；仍是独立 Vite 构建（避免桌面 CSS 冲突），原生路由迁移待后续。
- 公开运行 Gate 仍按 [`docs/产品与需求/手机端公开上线检查.md`](../../产品与需求/手机端公开上线检查.md) 执行。

## 7. 下一步

1. 手机 H5 路由并入主 SPA（`/m/*`），复用主站 Layout 与登录态。
2. 主站找回密码/邮箱验证；H5 不再保留独立 auth 逻辑。
3. 美股基本面：免费源或采购评估。
4. 主题/热点用真实行业指数与成分重算。
5. 真机、弱网、E2E 与公开 Gate。
