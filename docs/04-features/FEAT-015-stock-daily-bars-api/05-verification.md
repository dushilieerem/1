# 个股日线行情 API：Verification

## 自动化验证

- 2026-07-28：`ResearchEngine/tests/test_api.py` 通过，37 passed。
- 覆盖：股票代码列表的排序返回、OHLC 返回与日期筛选、未知代码、倒置日期、字段缺失，以及现有因子/策略 API 回归。

## 验收结论

`GET /api/market-data/symbols` 与 `GET /api/market-data/daily/{symbol}` 已实现，满足 MVP 的股票选择器数据、结构化 OHLC、明确错误语义和已发布 Parquet 数据边界。

## 已知验证限制

历史验证曾因第三方回测依赖初始化报错而中断；该依赖已从项目移除，后续全量回归不再受其影响。
