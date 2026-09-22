# 因子编写规范

> 适用对象：因子研究员
> 关联：[因子与策略指南目录](README.md)

## 1. 因子库与因子

因子库是前端管理的一组因子函数；研究员创建因子时只需填写函数，不需要编写 `FactorLibrary` 类或导入语句。每个因子输出“交易日 × 股票”的宽表。

新建因子的模板：

```python
def 因子名(self):
    """因子描述"""
    return
```

名称使用小写字母和下划线，例如 `momentum_20d`。函数可带默认参数，例如 `def momentum(self, window=20):`。

## 2. 示例

```python
def momentum_20d(self):
    """过去 20 个交易日收益率。"""
    return self.close.pct_change(20)

def volatility_20d(self):
    """过去 20 个交易日收益率波动率。"""
    return self.close.pct_change().rolling(20).std()

def bollinger_position(self, window=20, n_std=2.0):
    """收盘价在布林带中的相对位置。"""
    mid = self.close.rolling(window).mean()
    std = self.close.rolling(window).std()
    return (self.close - (mid - n_std * std)) / (2 * n_std * std)

def ep_ratio(self):
    """市盈率倒数。"""
    return 1.0 / self.pe_ttm
```

复杂逻辑允许使用多行中间变量，但最后必须返回宽表。

## 3. 当前因子面板字段

| 分类 | 字段 |
|------|------|
| 价格 | `open`、`high`、`low`、`close` |
| 成交 | `volume`、`amount`、`turnover` |
| 市值/股本 | `total_mv`、`float_mv`、`total_shares`、`float_shares` |
| 估值 | `pe_ttm`、`pb`、`ps_ttm` |
| 状态 | `is_st`、`limit_up` |

使用 `self.fields` 判断字段是否存在。缺失字段不能用最新静态值替代：应改用可用字段，或停止该因子的回测。

基准指数可用 `self.csi300.close`、`self.csi500.close`、`self.sse50.close` 与 `self.csi1000.close` 访问；与股票宽表计算时应按日期对齐：

```python
def relative_strength_vs_csi300(self, window=20):
    return self.close.pct_change(window).sub(
        self.csi300.close.pct_change(window), axis=0
    )
```

## 4. 编写规则

- 使用 pandas 向量化表达式，不逐只股票、逐日循环。
- 窗口期形成前产生的 `NaN` 可以保留，系统会处理。
- 不得使用未来数据，例如 `self.close.shift(-1)`。
- 参数应表达业务含义，例如 `window`、`n_std`，不要使用 `a`、`b`。
- 写清楚 docstring，它会作为因子说明展示。

## 5. 因子回测

通过 `POST /api/backtest/factor` 提交因子函数体和因子名。成功的必要条件是 HTTP `200` 且响应 `error` 为 `null`；HTTP `200` 但 `error` 非空代表业务执行失败。
