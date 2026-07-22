# SVQuant

因子研究薄前端：因子库 / 面板 / 检测 / 社区。  
本机**不存行情**；回测与试算走局域网 **YGQuant ResearchEngine**（默认 `192.168.3.64:9527`）。

## 目录

```
SVQuant/
├── frontend/          # Vite React  :9530
├── backend/           # 薄 API      :8766
│   ├── api_server.py
│   ├── factor/        # 官方因子 .py + index.yaml
│   ├── services/
│   ├── .env.example   # 复制为 .env（勿提交 .env）
│   └── requirements.txt
├── README.md
└── .gitignore
```

## 依赖（仅「自己部署」时需要）

- Python 3.10+（建议 conda：`conda create -n SVQuant python=3.11`）
- 本机 Postgres，库名建议 `svquant`（见 `.env.example`）
- 能访问 `192.168.3.64:9527`（`/api/health` 应返回正常）

## 首次配置（自己部署）

```powershell
cd backend
copy .env.example .env
# 编辑 .env：DATABASE_URL / JWT_SECRET / ADMIN_PASSWORD 等（填你自己机器上的库）

conda activate SVQuant
pip install -r requirements.txt
python scripts/init_community_db.py
```

## 启动（自己部署）

```powershell
# 终端 1 — 后端
cd backend
conda activate SVQuant
python -u api_server.py

# 终端 2 — 前端
cd frontend
npm install
npm run dev
```

- 本机：http://127.0.0.1:9530 · API http://127.0.0.1:8766  
- 自检：`curl http://127.0.0.1:8766/api/health` · `curl http://192.168.3.64:9527/api/health`

## 说明

- 自定义因子、因子检测按**登录用户**隔离；官方因子面板指标缓存在本机 SQLite（`backend/output/`，不入库）。
- 缺 RE 字段的价值类因子会标「数据不可用」，不会用其它指标顶替。

  ​
