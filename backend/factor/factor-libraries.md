# GET /api/factor-libraries

返回 ResearchEngine 当前已登记的全部内置因子库，供 SVQuant 构建“因子库”一级选择器。

该接口由 ResearchEngine 提供；SVQuant 不读取本地因子源码，也不执行官方因子。返回顺序按因子库名称升序排列。

## 请求

```http
GET /api/factor-libraries
```

无路径参数、查询参数和请求体。

## 响应

成功时返回 HTTP `200`：

```json
{
  "libraries": [
    {
      "name": "momentum_lib",
      "description": "动量/趋势类因子",
      "factor_count": 18,
      "tags": ["momentum", "trend", "reversal"]
    },
    {
      "name": "volatility_lib",
      "description": "波动率/风险类因子",
      "factor_count": 19,
      "tags": ["volatility", "risk"]
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `libraries` | object[] | 已登记的内置因子库列表。 |
| `libraries[].name` | string | 因子库名；回测时作为 `library_name` 传给 `/api/backtest/factor`。 |
| `libraries[].description` | string/null | 因子库说明，来自 `index.yaml`。 |
| `libraries[].factor_count` | integer | `index.yaml` 登记的因子数量。 |
| `libraries[].tags` | string[] | 因子库标签；没有标签时返回空数组。 |

本接口返回的是库级目录，不返回具体因子名称。SVQuant 选择因子库后，应继续请求
[`GET /api/factors/{library_name}`](factor-library-factors.md) 获取该库的因子列表。

## 错误

| HTTP 状态码 | 情况 |
|------------|------|
| `503` | ResearchEngine 因子库目录不可用或响应无效。 |

错误响应示例：

```json
{
  "detail": "ResearchEngine 因子库目录不可用"
}
```

## 与回测的关系

SVQuant 可以按以下顺序构建内置因子选择流程：

```text
GET /api/factor-libraries
        ↓ 用户选择 library_name
GET /api/factors/{library_name}
        ↓ 用户选择 factor_name
POST /api/backtest/factor
```

回测请求中的最小内置因子来源字段为：

```json
{
  "library_name": "momentum_lib",
  "factor_name": "momentum_5d"
}
```
