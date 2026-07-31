# 股指与成分股查询 API：Verification

## 自动化验证

- 2026-07-31：`conda run -n svquant python -m pytest ResearchEngine/tests/test_api.py -q -vv` 通过，53 passed。
- 2026-07-31：`conda run -n svquant python -m pytest -q` 通过，193 passed。
- 覆盖：可用股指列表、按 `000300.SH` 读取最新一期成分股、未知代码 `404` 与既有 API 回归。

## 验收结论

`GET /api/market-data/indices` 和 `GET /api/market-data/indices/{code}/constituents` 已实现。接口只读取当前已发布的本地数据；成分股明确为最新一期快照，并对未知代码和不可用数据提供明确错误语义。
