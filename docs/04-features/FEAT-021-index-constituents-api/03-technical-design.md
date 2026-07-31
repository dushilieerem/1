# 股指与成分股查询 API：Technical Design

`ResearchEngine.api.market_data` 保持 HTTP 适配层职责：复用按数据目录缓存的 `DataEngine(FieldParquetProvider)`；通过既有 `get_index` 判断已发布股指可用性，通过既有 `get_universe` 读取最新一期成分。证券名称继续从发布版 `stock_info.parquet` 映射，路由与 Pydantic 模型只负责契约和 JSON 序列化。

新增 GET 端点，不改动既有回测或个股行情契约。数据目录读取失败立即以 `503` 失败；回滚时移除两条路由即可。测试覆盖可用股指、最新快照、未知代码及现有 API 回归。
