# GET /api/factor-libraries

返回当前已登记的全部内置因子库，供 WebApp 构建“因子库”一级选择器。

该接口只读项目内 SQLite 因子库 `app/assets/factors/factor_library.db`，不会导入或执行因子
源码。路径可由 `SVQUANT_FACTOR_DB_PATH` 或 `SVQUANT_FACTOR_DB` 覆盖，返回顺序按库 ID 排列。

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
      "name": "主因子库",
      "description": "SQLite 因子库",
      "factor_count": 432,
      "tags": ["动量", "价值"]
    }
  ]
}
```
| 字段 | 类型 | 说明 |
|------|------|------|
| `libraries` | object[] | 已登记的内置因子库列表。 |
| `libraries[].name` | string | 因子库名；回测时作为 `library_name` 传给 `/api/backtest/factor`。 |
| `libraries[].description` | string/null | 因子库说明，来自 SQLite。 |
| `libraries[].factor_count` | integer | SQLite 中的因子数量。 |
| `libraries[].tags` | string[] | 从因子分类聚合的分类名称。 |

本接口返回的是库级目录，不返回具体因子名称。WebApp 选择因子库后，应继续请求
[`GET /api/factors/{library_name}`](factor-library-factors.md) 获取该库的因子列表。

## 错误

| HTTP 状态码 | 情况 |
|------------|------|
| `503` | SQLite 因子库不存在、无法打开或表结构不可用。 |

错误响应示例：

```json
{
  "detail": "因子库目录不可用: 因子数据库不存在: app/assets/factors/factor_library.db"
}
```

## 与回测的关系

WebApp 可以按以下顺序构建内置因子选择流程：

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
  "library_name": "主因子库",
  "factor_name": "SV01_0001"
}
```
