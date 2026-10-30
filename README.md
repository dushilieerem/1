# SVQuant

SVQuant 是量化投研产品层，负责 Web 界面、用户业务、权限、知识库和业务数据；
ResearchEngine 是独立的研究计算服务。两者通过 HTTP API 集成，SVQuant 不导入
ResearchEngine 的 Python 包，也不直接读取行情目录或回测结果 SQLite。

## 目录

```text
SVQuant/
├── frontend/          # 主 Web 前端，Vite，默认 :9530
├── backend/           # FastAPI 产品后端，默认 :8766
│   ├── app/            # 路由、启动和生命周期
│   ├── services/       # 用户、社区、因子/策略 BFF、ResearchEngine 网关
│   ├── ai/             # SVQuant 侧 AI 编排和供应商适配
│   ├── factor/         # 用户自定义因子同步产物与 API 文档
│   └── requirements.txt
├── KnowledgeHub/       # 知识库模块（API 挂载在 backend 的 /api/kh）
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
| `marketdata` | 外部数据/ResearchEngine 部署 | SVQuant 不保存、不读取 |
| 回测结果 SQLite | ResearchEngine 部署 | SVQuant 不直接访问，只接收 API 结果 |
| LLM、新闻等供应商 | SVQuant | 通过 `backend/.env` 配置敏感凭据 |

## 本地一键启动

准备好 PostgreSQL、ResearchEngine、`backend/.env` 和前端依赖后，在仓库根目录运行：

```bash
./scripts/svquant.sh
```

默认打开 <http://127.0.0.1:9530>。脚本会依次启动主前端、`backend`、`invest-api` 和手机 H5，
并可用 cloudflared 为主前端和 H5 各建一条临时外网通道（地址见 `./scripts/svquant.sh status`，
每次启动都会变）。未安装 cloudflared 时先运行 `./scripts/svquant.sh install-cloudflared`；
不需要外网访问用 `./scripts/svquant.sh start --no-tunnel`。状态、日志、停止和手动启动方式见[部署文档](docs/部署与运维/部署文档.md)。

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
curl http://127.0.0.1:8766/api/health
```

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

主前端默认地址为 <http://127.0.0.1:9530>，所有浏览器请求先访问 SVQuant
`/api`，再由后端网关调用 ResearchEngine。KnowledgeHub 前端如需单独运行：

```bash
cd KnowledgeHub/frontend
npm install
npm run dev
```

## 测试

测试命令、当前覆盖范围和环境限制见[测试设计](docs/测试设计/测试设计.md)。

完整产品、架构和交付文档见 [`docs/README.md`](docs/README.md)。



