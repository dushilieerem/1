# SVQuant Invest H5

独立手机版 H5（React 19 + Vite 8 + TypeScript），复用 SVQuant 账号。当前 29 只标的为**公开 EOD 数据**（腾讯 K 线 + 东方财富财务/估值），主题为成分股等权代理，公告/研报/要闻为公开标题；无实时、无推送。

## 运行

先启动 API（见 `../../invest-api/README.md`，默认 `127.0.0.1:8767`），再启动 H5：

```powershell
cd frontend/invest
..\node_modules\.bin\vite.cmd --host 127.0.0.1 --port 9540
```

打开 `http://127.0.0.1:9540/`，使用演示账号 `demo / demo1234`。

生产构建：

```powershell
..\node_modules\.bin\vite.cmd build
# dist/ 由 Nginx/CDN 托管；/api 反代到 invest-api
```

冒烟测试（需 API + H5 已启动，且本机有 Chrome）：

```powershell
node tests/smoke.mjs
```

> 本工程复用 `frontend/node_modules`（React/Vite/Router/lucide/lightweight-charts），没有单独安装依赖。换机器时需在 `frontend` 执行过一次 `npm install`。

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

## 明确不做

- 不接交易、不自动调仓、不接券商。
- 不做实时行情、不做分时、不做推送。
- 不做 AI 生成/多空辩论/社区/UGC/机构目标价/量化。
- 不做微信 JS-SDK/支付。

## 关键约束

- API 必须与 H5 同源反代，或把 H5 域名加入 `INVEST_CORS_ORIGINS`。
- 公开运行前必须完成数据源条款、ICP、隐私政策、用户协议与安全加固；见 `../../invest-api/PUBLIC_LAUNCH.md`。
- 所有页面标注“收盘数据 · 非实时 · 不构成投资建议”；行情/组合/主题为公开 EOD（主题为等权代理），公告/研报/要闻为公开标题；不要改回“AI”文案。

## 构建体积

当前首屏约 104KB gzip，K 线图表按需加载（约 55KB gzip）。后续可继续把财报/资讯 Sheet 做动态 import。
