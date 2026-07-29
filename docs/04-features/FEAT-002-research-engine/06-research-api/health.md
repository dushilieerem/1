# GET /api/health

用于负载均衡、部署探针和 WebApp 的服务可用性检查。

```http
GET /api/health
```

```json
{ "status": "ok", "version": "2.0.0", "engines": ["native", "vectorbt"] }
```

响应 `200` 表示 API 进程可响应。该端点不验证市场数据目录、可选引擎依赖或回测任务是否可用。
