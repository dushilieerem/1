# GET /api/market-data/indices/{code}/constituents

返回指定内置股指在当前已发布数据版本中的最新一期成分股。

```http
GET /api/market-data/indices/000300.SH/constituents
```

```json
{
  "index": {"code": "000300.SH", "name": "沪深300"},
  "constituents": [
    {"symbol": "000001.SZ", "name": "平安银行"}
  ],
  "unmapped_count": 0
}
```

`code` 使用股指代码；也兼容内部标识 `CSI300`、`CSI500`、`CSI1000` 和 `SSE50`。返回代码按字典序排序，证券代码统一附加交易所后缀。成分股来自指数成分 Parquet 的最新一期快照，不代表历史任意日期的成分；无效股指代码返回 `404`，成分文件或证券主数据不可读返回 `503`。
