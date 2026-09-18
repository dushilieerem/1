# KnowledgeHub（知识库平台）

路径：`SVQuant/KnowledgeHub/`

```
KnowledgeHub/
  frontend/          # Vite :9531
  backend/
    knowledge_hub/   # Python 包（分块 / 仓储 / HTTP handlers）
  docs/
```

- 前端：`frontend/` → `npm run dev` → **http://127.0.0.1:9531/**（端口可按部署调整）
- API：由 `SVQuant/backend/api_server.py`（8766）挂载 `/api/kh/*`，导入本目录 `backend/knowledge_hub`
- 仅 **admin**；SVQuant 个人中心有入口

文档：

- [使用说明.md](./docs/使用说明.md)（页面：`/settings/guide`）
- [API文档骨架.md](./docs/API文档骨架.md)（页面：`/settings/api`，含 search/ask）
- [分块策略扩展.md](./docs/分块策略扩展.md)
