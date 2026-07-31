# ResearchEngine HTTP API（FastAPI）

> 文档版本：v2.3
> 最后更新：2026-07-31

ResearchEngine 是无状态的研究计算服务：接收代码与参数、执行回测、返回结构化结果；不管理用户、因子/策略资产或回测结果持久化。开发期临时承载的 AI 因子草稿端点只生成并静态校验代码，不执行回测，待 SaaS 应用层具备身份与资产治理后迁出。

## 运行

```bash
pip install -e ".[api]"
uvicorn researchengine.api.app:app --reload
```

- Swagger UI：<http://localhost:8000/docs>
- ReDoc：<http://localhost:8000/redoc>

## API 索引

每个端点拥有独立契约文档；新增端点时必须新增独立页面并更新本表。

| 模块 | 方法 | 端点 | 文档 |
|------|------|------|------|
| 系统 | GET | `/api/health` | [健康检查](06-research-api/health.md) |
| AI 因子草稿 | POST | `/api/ai/factor-generations` | [AI 因子草稿生成](06-research-api/ai-factor-generations.md) |
| AI 策略草稿 | POST | `/api/ai/strategy-generations` | [AI 向量化策略草稿生成](06-research-api/ai-strategy-generations.md) |
| AI 回测解读 | POST | `/api/ai/backtest-interpretations` | [AI 回测解读与优化建议](06-research-api/ai-backtest-interpretations.md) |
| 市场数据 | GET | `/api/market-data/symbols` | [股票代码列表](06-research-api/market-data-symbols.md) |
| 市场数据 | GET | `/api/market-data/daily/{symbol}` | [个股日线](06-research-api/market-data-daily.md) |
| 因子回测 | POST | `/api/backtest/factor` | [因子回测](06-research-api/backtest-factor.md) |
| 策略资产 | GET | `/api/strategies` | [策略目录](06-research-api/strategy-list.md) |
| 策略回测 | POST | `/api/backtest/strategy` | [策略回测](06-research-api/backtest-strategy.md) |

## 共同约束

- 市场数据与回测均只读服务端配置的已发布历史 Parquet；当前优先使用环境变量 `SVQUANT_DATA_DIR`。用户资产的 CRUD、鉴权和资产引用解析均由 WebApp 负责；ResearchEngine 只接收已解析快照。
- 回测源码、数据读取或执行错误返回 HTTP `200` 并在响应 `error` 中说明；请求体不符合契约或含未知字段时返回 `422`。
- 当前仅支持同步回测。异步提交、`run_id` 查询和结果持久化尚未实现。
- 执行用户提交的 Python 源码具有任意代码执行风险；生产环境须使用子进程/容器隔离、资源限制、只读数据目录、无出网权限，并收紧 CORS 和鉴权。

## 包结构

```text
ResearchEngine/researchengine/api/
  app.py               FastAPI 应用工厂 + CORS
  routes.py            HTTP 路由
  schemas.py           Pydantic 请求/响应模型
  market_data.py       已发布市场数据查询
  runner.py            回测编排
  serializers.py       pandas/指标 → JSON
```

## 与前端的分工

前端负责股票选择、因子/策略资产管理、请求组装、结果展示与持久化；ResearchEngine 仅执行本页索引中的计算或只读数据查询，不保存任何业务状态。
