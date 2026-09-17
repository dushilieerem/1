# GET /api/market-data/symbols

返回当前已发布市场数据中可查询的全部股票代码，供 WebApp 构建股票选择器。

```http
GET /api/market-data/symbols
```

```json
{
  "symbols": [
    {"symbol": "000001.SZ", "name": "平安银行"},
    {"symbol": "600519.SH", "name": "贵州茅台"}
  ],
  "unmapped_count": 0
}
```

代码按 `symbol` 字典序去重排序，并统一附加交易所后缀：上交所 `.SH`、深交所 `.SZ`、北交所 `.BJ`。仅返回同时具备行情和名称映射、可直接供 WebApp 选择的标的；`unmapped_count` 表示因缺少名称映射而被排除的行情代码数量。不返回行业、实时状态或数据版本。数据目录、证券主数据或股票代码面板不可读时返回 `503`。
