# SVQuant Invest H5

独立手机版 H5（React 19 + Vite 8 + TypeScript），复用 SVQuant 主站账号。数据直接读主后端 PostgreSQL（`/api/invest/*`）：全市场 A 股/美股主数据、日线/估值/财务、指数与公告/研报/要闻。主题仍为成分股等权代理；无实时、无推送。

2026-10-30 起新增 AI 解读面板（个股/首页/组合），接口复用 `backend/ai/router`；合规红线仍强制，不提供买卖点/目标价/收益承诺。

## 运行

先启动主后端（`backend`，开发默认 `127.0.0.1:8768`，生产 `8766`），H5 与主后端同源：

```powershell
cd frontend/invest
..\node_modules\.bin\vite.cmd --host 127.0.0.1 --port 9540
```

打开 `http://127.0.0.1:9540/`，使用演示账号 `demo / demo1234`。

生产构建：

```powershell
..\node_modules\.bin\vite.cmd build
# dist/ 由 Nginx/CDN 托管；/api 反代到主后端
```

冒烟测试（需 API + H5 已启动，且本机有 Chrome）：

```powershell
node tests/smoke.mjs
```

> 本工程复用 `frontend/node_modules`（React/Vite/Router/lucide/lightweight-charts），没有单独安装依赖。换机器时需在 `frontend` 执行过一次 `npm install`。

## 数据与 PG 读模型

```bash
# 1) parquet → PG（A 股）
/home/dev01/program/anaconda3/bin/python scripts/etl_marketdata.py --from 2016-01-01
# 2) 美股（英文态研究范围）
/home/dev01/program/anaconda3/bin/python scripts/etl_us_marketdata.py --days 750
# 3) 财务/公告/总股本
/home/dev01/program/anaconda3/bin/python scripts/fetch_financials.py
/home/dev01/program/anaconda3/bin/python scripts/fetch_valuation_snapshot.py
# 4) 重建手机端服务层快照
/home/dev01/program/anaconda3/bin/python scripts/refresh_invest_serving.py
```

- 用户数据落 `invest_*` 表，不随快照重建覆盖。
- A 股 5,576 只、美股 16,273 只进入 `stocks`（代码规则：A 股/ETF 用裸代码，美股用 `AAPL.O` 全代码避免跨交易所重名）。
- 未同步日线的标的详情页返回「行情数据暂缺」空态，不再 500。

## 已实现（MVP）

- 登录/注册（演示 / 可通过 API 代理 SVQuant 账号；注册默认关闭）、风险测评、隐私/协议页。
- 首页：今日概览 3 件事、收盘复盘、指数条、热点、自选、术语入口。
- 热点：板块热度/估值分位、历史 base rate、相关标的、资讯。
- 个股：收盘报价九宫格、日/周/月 K（lightweight-charts）、MA/成交量、技术面、四 Tab（概览/财务/估值/风险）、财报/资讯 Sheet。
- 自选：分组、加/移、关注事件、收盘后触发日志。
- 组合：CSV/手工导入、风险分、诊断、行业暴露、持仓、配置偏离、压力测试、成本与换手。
- 搜索：股票/代码/拼音、预设条件（低估值/高动量/低波动）、加自选。
- 资讯：要闻/公告/研报，标题 + 来源 + 链接。
- 我的：数据口径、导出/删除 Invest 数据、隐私与协议。
- AI 解读：个股/首页/组合三个面板；数据来自当前页面读模型，输出带非投资建议声明。

## 明确不做

- 不接交易、不自动调仓、不接券商。
- 不做实时行情、不做分时、不做推送。
- 不做社区/UGC/机构目标价/量化模式。
- 不做微信 JS-SDK/支付。
- 不做「自动生成买卖点」类 AI；AI 只解释数据与风险。

## 关键约束

- API 必须与 H5 同源反代，或把 H5 域名加入 `INVEST_CORS_ORIGINS`。
- 公开运行前必须完成数据源条款、ICP、隐私政策、用户协议与安全加固；见 [`docs/产品与需求/手机端公开上线检查.md`](../../docs/产品与需求/手机端公开上线检查.md)。
- 所有页面标注“收盘数据 · 非实时 · 不构成投资建议”；行情/组合/主题为公开 EOD（主题为等权代理），公告/研报/要闻为公开标题。
- AI 面板必须保留「AI 生成 · 非投资建议」与数据口径；红线命中走固定话术。

## 构建体积

当前首屏约 104KB gzip，K 线图表按需加载（约 55KB gzip）。后续可继续把财报/资讯 Sheet 做动态 import。
