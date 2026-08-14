# GET /api/factors/{library_name}

返回指定内置因子库中的全部因子，供 WebApp 构建“因子”二级选择器。

该接口先根据 `Factor/libraries/index.yaml` 校验 `library_name`，再加载对应的
`FactorLibrary`，并校验源码发现的因子清单、因子数量和索引登记一致。接口不会执行因子计算或回测。

## 请求

```http
GET /api/factors/momentum_lib
```

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| `library_name` | 路径 | string | 是 | `Factor/libraries/index.yaml` 中登记的因子库名，例如 `momentum_lib`。 |

无查询参数和请求体。

## 响应

成功时返回 HTTP `200`：

```json
{
  "library_name": "momentum_lib",
  "factors": [
    {
      "name": "momentum_10d",
      "description": "10 日动量。"
    },
    {
      "name": "momentum_20d",
      "description": "20 日动量（约月）。"
    },
    {
      "name": "momentum_5d",
      "description": "5 日动量。"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `library_name` | string | 本次查询的因子库名。 |
| `factors` | object[] | 该库中可发现的全部公开因子方法。 |
| `factors[].name` | string | 因子方法名；回测时作为 `factor_name` 传给 `/api/backtest/factor`。 |
| `factors[].description` | string/null | 因子方法的 docstring 首行；没有说明时为 `null`。 |

当前接口只返回因子名称和说明，不返回 `index.yaml` 中的因子默认参数、逐因子标签或验证状态。
如果 WebApp 需要展示这些扩展元数据，应读取已发布的因子资产目录或后续增加专用详情接口，不能假设当前响应包含这些字段。

## 错误

| HTTP 状态码 | 情况 |
|------------|------|
| `404` | `library_name` 未在 `index.yaml` 中登记。 |
| `503` | 因子库索引、声明的 Python 文件或源码不可用；或源码与 `index.yaml` 未同步。 |

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
  "library_name": "momentum_lib",
  "factor_name": "momentum_5d",
  "portfolio_type": "long_only",
  "universe": "CSI300",
  "start": "2024-01-01",
  "end": "2024-02-01",
  "benchmark": "CSI300"
}
```

因子方法自身的默认参数由因子实现决定。例如 `momentum_5d` 使用其实现中定义的默认窗口；当前回测接口没有单独的动态因子参数字段。

