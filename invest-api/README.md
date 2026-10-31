# SVQuant Invest API

轻量 FastAPI + SQLite 的 Invest MVP 后端：收盘后演示数据、演示登录、规则摘要、组合体检、自选/事件、导出/删除。

## 运行

```powershell
conda activate svquant
cd invest-api
python seed.py --force
python -m uvicorn app:app --host 127.0.0.1 --port 8767
```

- API 文档：`http://127.0.0.1:8767/docs`
- 健康检查：`http://127.0.0.1:8767/api/health`
- 演示账号：`demo / demo1234`

测试：

```powershell
python -m pytest tests -q
```

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `INVEST_DB` | `data/invest.db` | SQLite 路径 |
| `INVEST_JWT_SECRET` | 开发默认值 | **公开环境必须设置强随机值** |
| `INVEST_CORS_ORIGINS` | `http://127.0.0.1:9540,http://localhost:9540` | 跨域白名单；同源反代可不配 |
| `INVEST_RESEED` | `0` | `1` 时启动重建演示数据 |
| `INVEST_ENV` | 空 | `production` 时关闭 `/docs`、`/openapi.json`、`/redoc` |
| `SVQUANT_API_BASE` | 空 | 设置后，非 demo 账号走 SVQuant `/api/auth/login` 校验；注册走 `/api/auth/register`；SSO 走 `/api/auth/sso`；H5 另发 Invest token |
| `SVQUANT_WEB_URL` | 空 | 预留给主站链接；当前 H5 用本地 `/register` |

## 鉴权

- 默认 `demo / demo1234`，签本地 HS256 token（7 天）。
- 登录接口有进程内限流（20 次/分钟/IP）；注册共用同一限流；公开环境仍需 Nginx/WAF/验证码/Redis 限流。
- 设置 `SVQUANT_API_BASE` 后：
  - `POST /api/auth/login` 服务端调用 SVQuant 登录；
  - `POST /api/auth/register` 服务端调用 SVQuant 注册，成功后直接签发 Invest token；
  - 成功则给同一用户签发 Invest token；
  - **SSO**：支持主站 token-exchange（`POST /api/auth/sso`）；主站可跳转 `#svq_token=...`；不做 cookie SSO，H5 仍是独立会话。
- H5 token 存 `sessionStorage`，按标签页隔离；401 自动清理。
- `INVEST_ENV=production` 时若未设置 `INVEST_JWT_SECRET` 会拒绝启动；认证/账户响应带 `Cache-Control: no-store`。
- 登录/注册/导出/删除写入 `auth_events`（时间、动作、用户名、IP、摘要）；公开环境需接审计留存与脱敏策略。

## 数据

> 2026-10-30 起，生产/开发数据由 `scripts/sync_invest_sqlite.py` 从 PostgreSQL 服务层同步到 SQLite 读取缓存；`seed.py` 仅用于首建库与演示回退。

- `seed.py` 生成**确定性演示数据**：29 只标的、750 交易日、8 季财务、3 个主题、新闻、示例组合、事件与风测。
- `scripts/sync_invest_sqlite.py`：全市场证券主表 + 选中池日线/估值/财务 + 指数 + 公告/研报/要闻；用户数据不覆盖。
- `scripts/fetch_live.py` 用腾讯 K 线 + 东方财富财务/估值，把 29 只标的替换为真实 EOD（示范命令见上）。已实测成功：801 根日线、2000+ 条 PE/PB、50 期财务，数据日 2026-10-29；beta 按近 1 年日收益 vs 沪深300 实算。
- `scripts/fetch_akshare.py` 是 AKShare 接入脚手架；当前环境 AKShare 的 `stock_zh_a_hist` / `stock_zh_a_spot_em` 返回 `RemoteDisconnected`，未采用。
- 主题指数/base rate 为成分股等权代理（非官方指数）；公告/研报/要闻已接东方财富公开标题+链接。正式上线前需逐源核对条款。
- 每日任务：`scripts/run_daily.ps1`（Windows Task Scheduler）或 `run_daily.sh`（cron `30 18 * * 1-5`）；包含 `fetch_live.py` + `fetch_news.py`。
- 真实数据接入后仍需：复权/停牌/财务披露日/估值分位/数据质量检查、任务失败告警。
- `meta` 返回 `ageDays/isStale`（>2 天），H5 首页会提示数据过期。

## 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/register` | 注册（代理主站，默认演示环境关闭） |
| POST | `/api/auth/sso` | 主站 token exchange（需 `SVQUANT_API_BASE`） |
| GET | `/api/auth/me` | 当前用户 |
| GET | `/api/invest/home` | 首页日报/复盘/热点/自选 |
| GET | `/api/invest/meta` | 数据日期/来源/是否演示 |
| GET | `/api/invest/data-quality` | 日线/财务/估值/ETF 口径检查 |
| GET | `/api/invest/topic/{id}` | 热点与 base rate |
| GET | `/api/invest/stock/{code}?period=daily` | 个股行情/财务/估值/风险 |
| GET | `/api/invest/search?q=` | 搜索 + 预设条件 |
| GET | `/api/invest/news?kind=` | 资讯 |
| GET/POST/DELETE | `/api/invest/watchlist` | 自选 |
| POST | `/api/invest/events` | 关注事件 |
| GET | `/api/invest/portfolio` | 组合体检 |
| POST | `/api/invest/portfolio/import` | 导入持仓 |
| GET | `/api/invest/risk-profile` / POST | 风测 |
| GET | `/api/invest/account/export` | 导出 Invest 数据（含审计事件，不含 IP） |
| DELETE | `/api/invest/account/data` | 删除 Invest 数据（不删 SVQuant 账号） |

## AI 接口（复用 backend/ai/router）

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

- 需要 `backend/.env` 的 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`；未配置时返回 503。
- 前置红线（买入/卖出/目标价/保证收益/自动交易…）固定话术；后置扫描越界表达。
- 设计见 `docs/模块设计/AI与Agent模块/机构端与手机端Agent设计.md`。

## 已知缺口

- 真实数据覆盖 29 只标的；公告/研报/要闻为公开标题；主题为成分股等权代理；每日脚本已有但未安装调度器。
- 没有 Postgres（当前 SQLite）；注册代理已实现但默认关闭，找回密码、SVQuant 账号注销未做。
- 没有 WAF/验证码/完整限流（仅登录 20 次/分钟内存限流）。
- 没有推送、实时行情、分时、AI、社区/UGC、机构目标价、量化。
- 没有 CI/CD、容器化、备份脚本。

公开上线检查见 `PUBLIC_LAUNCH.md`。
