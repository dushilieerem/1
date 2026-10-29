# 因子编写规范

> 适用对象：在因子库中编写因子的研究员
> 关联：[因子与策略指南目录](README.md)

## 1. 因子库与因子

因子库是页面上管理的一组因子函数。新建因子时只需要填写函数本身，不需要写类定义、导入语句或文件头。

新建因子的模板：

```python
def 因子名(self):
    """因子描述"""
    return
```

名称使用小写字母和下划线，例如 `momentum_20d`。函数可以带默认参数，例如 `def momentum(self, window=20):`。

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

def small_size(self):
    """小市值因子：负的总市值。"""
    return -self.current_mv

def ep_ratio(self):
    """市盈率倒数。"""
    return 1.0 / self.pe_ttm
```

复杂逻辑可以使用多行中间变量，但最后必须返回“交易日 × 股票”的宽表。

## 3. 可用字段

| 分类 | 字段 |
|------|------|
| 价格 | `open`、`high`、`low`、`close` |
| 成交 | `volume`、`amount`、`turnover` |
| 市值 | `current_mv`（当前总市值，单位元） |
| 估值 | `dividend_yield_ttm`、`pe_ttm`、`pb_mrq`、`pcf_operating_cash_flow_ttm` |
| 状态 | `listed_status`、`the_sw_industry_code`、`up_and_down_status` |

- 市值字段名是 `current_mv`，没有 `total_mv`；市净率是 `pb_mrq`，没有 `pb`。
- 其他字段可以用 `self["字段名"]` 访问，全部可用字段名可以通过 `self.fields` 查看。
- 字段缺失时不要用最新静态值替代：改用可用字段，或停止该因子的回测。

基准指数可以用 `self.csi300.close`、`self.csi500.close`、`self.sse50.close` 与 `self.csi1000.close` 访问；与股票宽表计算时应按日期对齐：

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

## 5. 在页面里运行因子

1. 在「因子 → 因子库」保存因子，或在因子检测页直接编辑代码。
2. 打开「因子 → 检测报告」，选择因子、股票池、回测区间和检测深度后开始运行。
3. 运行是后台任务，页面会显示进度；完成后可以查看分层收益、IC 等结果。
4. 运行失败时页面会显示原因，例如“字段不存在”或语法错误。按提示修改代码后重新运行即可。
