# 个股日线行情 API：Verification

## 自动化验证

- 2026-07-28：`ResearchEngine/tests/test_api.py` 通过，37 passed。
- 覆盖：股票代码列表的排序返回、OHLC 返回与日期筛选、未知代码、倒置日期、字段缺失，以及现有因子/策略 API 回归。

## 验收结论

`GET /api/market-data/symbols` 与 `GET /api/market-data/daily/{symbol}` 已实现，满足 MVP 的股票选择器数据、结构化 OHLC、明确错误语义和已发布 Parquet 数据边界。

## 已知验证限制

全量 `pytest` 在收集 `QuantCore/tests/test_adapter.py` 时因环境中 `vectorbt` / Numba 缓存初始化报错而中断，未进入本 Feature 的用例；该错误与本次接口实现无关，需在测试环境修复可选 VectorBT 依赖后再做全量回归。
