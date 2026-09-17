# GET /api/factors/{library_name}

返回指定内置因子库中的全部因子，供 WebApp 构建“因子”二级选择器。

该接口从项目内 SQLite 因子库读取 `library_name` 对应的元数据，不执行因子计算或回测。默认数据库
为 `app/assets/factors/factor_library.db`，可由 `SVQUANT_FACTOR_DB_PATH` 或 `SVQUANT_FACTOR_DB` 覆盖。

## 请求

```http
GET /api/factors/主因子库
```

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| `library_name` | 路径 | string | 是 | SQLite `factor_libraries.library_name`，例如 `主因子库`。 |

无查询参数和请求体。

## 响应

成功时返回 HTTP `200`：

```json
{
  "library_name": "主因子库",
  "factors": [
    {
      "name": "SV01_0001",
      "description": "SQLite 中的因子说明",
      "factor_id": "SV01_0001",
      "display_name": "涨跌日频率差",
      "name_en": "Up-Down Day Frequency Gap",
      "category_name": "动量因子"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `library_name` | string | 本次查询的因子库名。 |
| `factors` | object[] | SQLite 中该库的全部因子元数据。 |
| `factors[].name` | string | 稳定 `sv_id`；回测时建议作为 `factor_name` 传给 `/api/backtest/factor`。 |
| `factors[].description` | string/null | SQLite 因子说明。 |
| `factors[].factor_id` | string/null | 稳定因子 ID，当前与 `sv_id` 相同。 |
| `factors[].display_name` | string/null | 中文展示名称。 |
| `factors[].name_en` | string/null | 英文展示名称。 |
| `factors[].category_name` | string/null | 所属分类名称。 |

当前接口返回目录元数据，但不返回因子源码和公共算子实现。因子参数由源码默认值决定，当前回测接口
没有单独的动态参数字段。

## 错误

| HTTP 状态码 | 情况 |
|------------|------|
| `404` | `library_name` 未在 SQLite `factor_libraries` 中登记。 |
| `503` | SQLite 因子库不存在、无法打开或表结构不可用。 |

未知因子库示例：

```json
{
  "detail": "未找到内置因子库: not_a_factor_library"
}
```

## 与回测的关系

WebApp 从响应中选择一个因子后，将库名和因子名放入因子回测请求；不需要提交
`factor_code`：

```json
{
  "library_name": "主因子库",
  "factor_name": "SV01_0001",
  "portfolio_type": "long_only",
  "universe": "CSI300",
  "start": "2024-01-01",
  "end": "2024-02-01",
  "benchmark": "CSI300"
}
```

因子方法自身的默认参数由因子实现决定。例如 `momentum_5d` 使用其实现中定义的默认窗口；当前回测接口没有单独的动态因子参数字段。
