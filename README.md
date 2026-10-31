# SVQuant

SVQuant 是量化投研产品层，负责 Web 界面、用户业务、权限、知识库和业务数据；
ResearchEngine 是独立的研究计算服务。两者通过 HTTP API 集成，SVQuant 不导入
ResearchEngine 的 Python 包，也不直接读取行情目录或回测结果 SQLite。

## 目录

```text
SVQuant/
├── frontend/          # 主 Web 前端，Vite，开发默认 :9531（生产 :9530）
├── backend/           # FastAPI 产品后端，开发默认 :8768（生产 :8766）
│   ├── app/            # 路由、启动和生命周期
│   ├── services/       # 用户、社区、因子/策略 BFF、ResearchEngine 网关
│   ├── ai/             # SVQuant 侧 AI 编排和供应商适配
│   ├── factor/         # 用户自定义因子同步产物与 API 文档
│   └── requirements.txt
├── KnowledgeHub/       # 知识库模块（API 挂载在 backend 的 /api/kh）
├── invest-api/         # 手机 H5 BFF（FastAPI + SQLite 读取缓存）
├── scripts/            # 启动、数据同步、建库脚本
├── docs/               # SVQuant 产品、架构和交付文档
└── .gitignore
```

内置策略元数据由 ResearchEngine API 同步到 SVQuant PostgreSQL 的
`builtin_strategies` 表；SVQuant 不再维护本地内置策略源码目录。策略执行和回测由
ResearchEngine 完成。

## 外部服务与数据边界

| 资源 | 负责人 | SVQuant 的使用方式 |
|------|--------|-------------------|
| PostgreSQL | SVQuant | 用户、认证、社区、知识库、因子/策略配置、审计日志 |
| ResearchEngine HTTP API | ResearchEngine | 通过 `backend` 网关调用因子、策略、行情和回测接口 |
| `marketdata` parquet | 外部数据/ResearchEngine 部署 | `scripts/etl_marketdata.py` 只读同步到 SVQuant PG 服务层；不修改源文件 |
| 回测结果 SQLite | ResearchEngine 部署 | SVQuant 不直接访问，只接收 API 结果 |
| LLM、新闻等供应商 | SVQuant | 通过 `backend/.env` 配置敏感凭据 |

## 本地一键启动

准备好 PostgreSQL、ResearchEngine、`backend/.env` 和前端依赖后，在仓库根目录运行：

```bash
./scripts/svquant.sh
```

默认打开 <http://127.0.0.1:9531>。脚本会依次启动主前端、`backend`、`invest-api` 和手机 H5，
并可用 cloudflared 为主前端和 H5 各建一条临时外网通道（地址见 `./scripts/svquant.sh status`，
每次启动都会变）。未安装 cloudflared 时先运行 `./scripts/svquant.sh install-cloudflared`；
不需要外网访问用 `./scripts/svquant.sh start --no-tunnel`。状态、日志、停止和手动启动方式见[部署文档](docs/部署与运维/部署文档.md)。

### 开发库（首次）

开发环境使用独立的 `svquant_dev` 库，不与生产的 `svquant` 共用数据；手机 H5 使用
`invest-api/data/invest.dev.db`，缺少时首次启动自动从种子数据生成。

首次准备：

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env，将 DATABASE_URL 的库名写成 svquant_dev（账号/密码/主机不变）
./scripts/init-dev-db.sh
```

脚本从 `backend/.env` 的 `DATABASE_URL` 取账号和主机，在同一个 PostgreSQL 实例里
幂等创建开发库（已存在则跳过）。库名可用 `SVQUANT_DEV_DB_NAME` 覆盖，Conda 环境可用
`SVQUANT_CONDA_ENV` 指定。

### 真实数据与 AI（2026-10-30）

```bash
# 1) parquet → PostgreSQL 服务层（A 股 2016 起；首次/数据 release 更新后跑）
/home/dev01/program/anaconda3/bin/python scripts/etl_marketdata.py --from 2016-01-01

# 2) 东方财富财务三表 + 公告（默认 8 只 A 股池；按需改 --symbols）
/home/dev01/program/anaconda3/bin/python scripts/fetch_financials.py

# 2.5) 总股本 / 总市值（研究池逐只快照）
/home/dev01/program/anaconda3/bin/python scripts/fetch_valuation_snapshot.py

# 3) PostgreSQL → 手机 H5 的 SQLite 读取缓存（用户数据不覆盖）
/home/dev01/program/anaconda3/bin/python scripts/sync_invest_sqlite.py \
  --db invest-api/data/invest.dev.db --limit-symbols 500

# 或一键（不含 parquet）：
./scripts/refresh_invest_data.sh

# 4) AI：backend/.env 配置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
#    手机端 /api/invest/ai/*，机构端 /api/inst/*，均复用 backend/ai/router
```

文档：

- [数据接入与库表设计](docs/数据设计/机构端与手机端-数据接入与库表设计-v0.1.md)
- [机构端与手机端 Agent 设计](docs/模块设计/AI与Agent模块/机构端与手机端Agent设计.md)
- [FEAT-034 机构端首版闭环](docs/功能包/FEAT-034-机构端首版闭环/README.md)

## 后端配置与手动启动

首次部署时人工创建配置：

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env，至少填写 DATABASE_URL、JWT_SECRET、YG_RE_BASE 等配置

conda activate svquant
cd backend
pip install -r requirements.txt
python -u api_server.py
```

ResearchEngine 地址只通过 `backend/.env` 的 `YG_RE_BASE` 配置。SVQuant 不提供
ResearchEngine 的安装或启动脚本；ResearchEngine 应在其独立仓库中单独部署。

健康检查：

```bash
curl http://127.0.0.1:8768/api/health
```

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

主前端开发默认地址为 <http://127.0.0.1:9531>，所有浏览器请求先访问 SVQuant
`/api`，再由后端网关调用 ResearchEngine。KnowledgeHub 前端如需单独运行：

```bash
cd KnowledgeHub/frontend
npm install
npm run dev
```

## 测试

测试命令、当前覆盖范围和环境限制见[测试设计](docs/测试设计/测试设计.md)。

完整产品、架构和交付文档见 [`docs/README.md`](docs/README.md)。



