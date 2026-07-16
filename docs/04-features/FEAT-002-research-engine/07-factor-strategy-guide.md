# 因子与策略编写规范

> 文档版本：v1.0
> 最后更新：2026-07-15
> 适用平台：SVQuant ResearchEngine v2.0
> 目标读者：量化研究员

---

## 目录

1. [概述](#1-概述)
2. [用户视角：因子库和因子是什么](#2-用户视角因子库和因子是什么)
3. [因子模板与编写规范](#3-因子模板与编写规范)
4. [可用数据字段](#4-可用数据字段)
5. [编写最佳实践](#5-编写最佳实践)
6. [前端映射关系（供前端/后端开发参考）](#6-前端映射关系供前端后端开发参考)
7. [策略编写规范](#7-策略编写规范)
8. [自定义策略（高级）](#8-自定义策略高级)
9. [完整示例](#9-完整示例)
10. [常见问题](#10-常见问题)

---

## 1. 概述

SVQuant 的因子和策略都是 **Python 代码**。研究员通过编写 Python 源码定义因子逻辑，提交到 ResearchEngine 执行回测。

**因子写法**：用户只需写一个函数，系统自动处理类、导入等样板代码。

**策略**：

| 方式 | 说明 |
|------|------|
| **默认策略**（FactorQuantileStrategy） | 系统内置，按因子值排序选股，无需编写策略代码 |
| **自定义策略**（高级） | 研究员编写完整的策略 Python 代码 |

---

## 2. 用户视角：因子库和因子是什么

### 2.1 因子库 = 文件夹

用户在前台点击 **"新建因子库"**，输入名称，就创建了一个因子库。

```
我的因子库                    ← 用户点击"新建因子库"创建
├── 动量选股                  ← 因子库（文件夹）
│   ├── 5日动量               ← 因子
│   └── 20日动量
├── 价值选股                  ← 因子库（文件夹）
│   ├── 低市盈率
│   └── 高股息
└── 基本面因子                ← 因子库（文件夹）
    ├── ROE因子
    └── 毛利率因子
```

**用户不需要写任何代码来创建因子库。** 系统自动生成背后的 Python 类。

### 2.2 因子 = 预填模板的函数

用户在某个因子库中点击 **"新建因子"**，输入因子名，系统自动生成模板：

```python
def 用户输入的因子名(self):
    """因子描述"""
    return 
```

用户只需要做两件事：

| 步骤 | 用户操作 | 示例 |
|------|---------|------|
| ① 写描述 | 在 `""" """` 中写因子说明 | `"""5 日动量因子"""` |
| ② 写表达式 | 在 `return` 后面写因子计算公式 | `return self.close.pct_change(5)` |

**完整的因子 = 函数名 + 描述 + 一行 return。**

### 2.3 用户不需要关心的东西

以下内容由系统自动处理，用户完全看不到：

```python
# 这些用户不需要写，不需要看到
from quantcore import FactorLibrary

class 某某因子库(FactorLibrary):
    author = "用户"
    
    # 用户只看到这个函数体
```

---

## 3. 因子模板与编写规范

### 3.1 新建因子时的模板

用户点击"新建因子"，系统弹出编辑框，内容如下：

```python
def 因子名(self):
    """因子描述"""
    return 
```

用户需要填写：

| 占位 | 用户填入 | 示例 |
|------|---------|------|
| `因子名` | 因子名称（小写字母+下划线） | `momentum_5d` |
| `"""因子描述"""` | 因子说明（会显示在因子列表中） | `"""5 日动量因子。"""` |
| `return ` 后面 | 因子计算公式 | `self.close.pct_change(5)` |

### 3.2 完整的因子示例

用户写完后的样子：

```python
def momentum_5d(self):
    """5 日动量因子：过去 5 个交易日的收益率。"""
    return self.close.pct_change(5)


def momentum_20d(self):
    """20 日动量因子。"""
    return self.close.pct_change(20)


def reversal_5d(self):
    """5 日反转因子：负收益率，做多跌得多的。"""
    return -self.close.pct_change(5)


def volatility_20d(self):
    """20 日波动率因子：收益率标准差。"""
    return self.close.pct_change().rolling(20).std()


def volume_ratio(self):
    """量比：当日成交量 / 5 日均量。"""
    return self.volume / self.volume.rolling(5).mean()


def bollinger_position(self):
    """布林带位置：（收盘价 - 下轨）/（上轨 - 下轨）。"""
    mid = self.close.rolling(20).mean()
    std = self.close.rolling(20).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    return (self.close - lower) / (upper - lower)


def market_cap(self):
    """市值因子：负总市值（偏好小市值）。"""
    return -self.total_mv


def ep_ratio(self):
    """EP 因子：市盈率倒数。"""
    return 1.0 / self.pe_ttm
```

### 3.3 带参数的因子

如果因子需要参数，在函数名后加括号写参数和默认值：

```python
def momentum(self, window=5):
    """动量因子：过去 window 个交易日的收益率。"""
    return self.close.pct_change(window)


def bollinger(self, window=20, n_std=2.0):
    """布林带位置因子。"""
    mid = self.close.rolling(window).mean()
    std = self.close.rolling(window).std()
    return (self.close - mid) / (std * n_std)
```

用户在前台编辑因子时，参数也会自动识别并展示：

```
因子名: momentum
参数: window=5
描述: 动量因子
公式: self.close.pct_change(window)
```

### 3.4 多行因子

如果因子逻辑较复杂，可以写多行——只需确保最后一行是 `return`：

```python
def macd(self):
    """MACD 因子。"""
    ema12 = self.close.ewm(span=12).mean()
    ema26 = self.close.ewm(span=26).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9).mean()
    return dif - dea


def quality_score(self):
    """质量因子：结合 ROE 和负债率。"""
    if "roe" in self.fields:
        return self["roe"]
    return self.close.pct_change(20).rolling(60).std() * (-1)
```

### 3.5 关键规则总结

| 规则 | 说明 |
|------|------|
| ✅ 因子名用**小写字母 + 下划线** | `momentum_5d`, `alpha101_001` |
| ✅ 写 `"""描述"""` | 会显示在因子列表中 |
| ✅ `return` 后面写向量化表达式 | 系统自动处理 NaN |
| ✅ 需要参数就写 `(self, window=5)` | 前台自动识别参数 |
| ✅ 多行时最后一行是 `return` | 前面的行是中间变量 |
| ❌ 不要用 `self._panel` | 系统自动绑定数据 |
| ❌ 不要逐行/逐只循环 | 永远向量化操作 |

### 3.6 删除/重命名因子

| 操作 | 前台操作 | 后台效果 |
|------|---------|---------|
| 删除因子 | 选中因子 → 右键/按钮 → 删除 | 从因子库文件中移除该方法 |
| 重命名因子 | 双击因子名 → 编辑 → 确认 | 修改方法名 |
| 删除因子库 | 选中因子库 → 删除 | 删除整个 .py 文件 |
| 重命名因子库 | 双击库名 → 编辑 → 确认 | 重命名 .py 文件 |

---

## 4. 可用数据字段

以下字段可通过 `self.<字段>` 在因子方法中访问。

### 4.1 价格数据

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `open` | float | 开盘价（元） | 10.50 |
| `high` | float | 最高价（元） | 11.20 |
| `low` | float | 最低价（元） | 10.30 |
| `close` | float | 收盘价（元） | 10.80 |
| `pre_close` | float | 前收盘价（元） | 10.50 |
| `adj_factor` | float | 复权因子 | 1.5 |

### 4.2 成交数据

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `volume` | float | 成交量（股） | 5000000 |
| `amount` | float | 成交额（元） | 54000000 |
| `turnover` | float | 换手率（%） | 2.5 |

### 4.3 市值与股本

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `total_mv` | float | 总市值（元） | 5e10 |
| `float_mv` | float | 流通市值（元） | 3e10 |
| `total_shares` | float | 总股本（股） | 5e9 |
| `float_shares` | float | 流通股本（股） | 3e9 |

### 4.4 估值数据

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `pe_ttm` | float | 滚动市盈率 | 15.0 |
| `pe` | float | 市盈率（静态） | 14.5 |
| `pb` | float | 市净率 | 2.0 |
| `ps_ttm` | float | 滚动市销率 | 1.5 |
| `pcf_ttm` | float | 滚动市现率 | 8.0 |

### 4.5 状态标记

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `is_st` | int8 | 是否 ST（1/0/NA） | 0 |
| `limit_up` | int8 | 是否涨停（1/0/NA） | 0 |
| `limit_down` | int8 | 是否跌停（1/0/NA） | 0 |
| `is_suspended` | int8 | 是否停牌（1/0/NA） | 0 |

### 4.6 访问不存在字段

```python
# 用 self.fields 查看当前所有可用字段
if "pe_ttm" in self.fields:
    ep = 1.0 / self.pe_ttm
else:
    ep = 0  # 兜底
```

---

## 5. 编写最佳实践

### 5.1 向量化优先

因子计算是**批量矩阵运算**，不要逐行/逐只循环：

```python
# ✅ 正确：向量化
def good_factor(self):
    return self.close.pct_change(5) - self.close.pct_change(20)

# ❌ 错误：逐只循环
def bad_factor(self):
    result = ...  # 不要这样写
    for col in self.close.columns:
        ...
    return result
```

### 5.2 处理 NaN

因子值允许 NaN，系统会自动处理。不需要特意填充：

```python
def factor_with_nan(self):
    # pct_change 在窗口期前会产生 NaN，系统会处理
    return self.close.pct_change(5)
```

### 5.3 参数命名

参数名应反映其含义：

```python
# ✅ 清晰
def momentum(self, window=5, decay_rate=0.5):

# ❌ 不清晰
def momentum(self, a=5, b=0.5):
```

### 5.4 文档字符串

写清晰的因子描述，会显示在因子列表中：

```python
def rsi(self, window=14):
    """相对强弱指标（RSI），衡量近期价格变动速度。"""
    delta = self.close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = -delta.clip(upper=0).rolling(window).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)
```

### 5.5 避免未来信息

因子在日期 t 只能使用 t 时刻及之前的数据：

```python
# ✅ 正确：只用到 t 时刻的数据
def momentum(self, window=5):
    return self.close.pct_change(window)

# ❌ 错误：使用了未来信息
def future_leak(self):
    return self.close.shift(-1) - self.close  # shift(-1) 用了明天的数据
```

---

## 6. 前端映射关系（供前端/后端开发参考）

### 6.1 用户操作 → 后台文件系统

```
前台用户操作                    后台文件系统
────────────────────────────────────────────────────
用户点击"新建因子库"          创建目录 + .py 文件
  → 输入名称 "动量因子"          → Factor/libraries/momentum_lib.py

用户点击"新建因子"            追加方法到 .py 文件
  → 选择因子库 "动量因子"         → 在 momentum_lib.py 中追加
  → 输入因子名 "momentum_5d"       def momentum_5d(self):
                                       """因子描述"""
                                       return 

用户编辑因子函数体              修改 .py 文件中对应方法
  → 填写 return 表达式             return self.close.pct_change(5)

用户删除因子                    从 .py 文件中移除该方法

用户删除因子库                  删除整个 .py 文件

用户重命名因子                  修改方法名

用户重命名因子库                重命名 .py 文件
```

### 6.2 文件结构示例

```
Factor/libraries/                    ← 因子库目录（由前端管理）
├── alpha_library.py                 ← 内置因子库（系统自带）
├── momentum_lib.py                  ← 用户创建的"动量因子"库
│   # from quantcore import FactorLibrary  ← 系统自动生成
│   # class MomentumLib(FactorLibrary):    ← 系统自动生成
│   #     author = "用户"                   ← 系统自动生成
│   def momentum_5d(self):
│       """5日动量"""
│       return self.close.pct_change(5)
│   def momentum_20d(self):
│       """20日动量"""
│       return self.close.pct_change(20)
│
├── value_lib.py                     ← 用户创建的"价值因子"库
│   def pe_inverse(self):
│       """EP因子"""
│       return 1.0 / self.pe_ttm
│   def pb_inverse(self):
│       """PB倒数"""
│       return 1.0 / self.pb
│
└── custom/                          ← 用户自定义（按需组织）
    └── my_strategy.py
        def my_alpha(self):
            return self.close.pct_change(5) * self.volume.rolling(5).mean()
```

### 6.3 系统自动生成的样板代码

前端保存因子时，需要将用户写的函数体包装成完整的 Python 文件：

```python
# 系统自动生成的文件头
from quantcore import FactorLibrary

class 库名(FactorLibrary):
    author = "当前用户"
    
    # 这里插入用户写的所有因子函数
    # （用户只看到这些函数体）
```

具体规则：

| 生成项 | 规则 | 示例 |
|-------|------|------|
| `from quantcore import FactorLibrary` | 每个文件顶部固定 | — |
| 类名 | 库名转大驼峰 + Library | `momentum_lib` → `MomentumLib` |
| `author` | 当前登录用户名 | `"张三"` |
| 方法 | 用户编辑的函数体，直接插入 | `def momentum_5d(self): ...` |

---

## 7. 策略编写规范

### 7.1 默认策略（无需编写）

SVQuant 内置 **FactorQuantileStrategy**（因子分位选股策略），按以下规则自动构建组合：

1. 按因子值从高到低排序
2. 取前 `stock_num` 只股票
3. 按因子值加权或等权分配权重
4. 按 `rebalance` 频率调仓

只需指定参数即可：

```json
{
    "factor_code": "...",
    "factor_name": "momentum_5d",
    "universe": "CSI500",
    "rebalance": "monthly",
    "stock_num": 100,
    "long_short": true
}
```

这是绝大多数场景的推荐方式。

### 7.2 策略参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `rebalance` | str | `monthly` | 调仓频率：`monthly` \| `weekly` \| `daily` |
| `stock_num` | int | 100 | 持仓标的数量 |
| `long_short` | bool | true | `true`=多空各半 \| `false`=只做多 |
| `commission_rate` | float | 0.0 | 手续费率（如 0.0003 = 万三） |
| `slippage_rate` | float | 0.0 | 滑点率（如 0.001 = 千一） |
| `initial_capital` | float | 1000000 | 初始资金（元） |

### 7.3 调仓规则

| 参数 | 行为 |
|------|------|
| `rebalance=monthly` | 每月第一个交易日调仓 |
| `rebalance=weekly` | 每周一调仓（如周一非交易日则顺延） |
| `rebalance=daily` | 每个交易日调仓 |
| `long_short=true` | 多头买入 top `stock_num/2` 只，空头卖出 bottom `stock_num/2` 只 |
| `long_short=false` | 仅做多，买入 top `stock_num` 只 |

---

## 8. 自定义策略（高级）

如需完全自定义策略逻辑（非简单的因子分位选股），可编写策略代码提交。

### 8.1 策略接口

```python
import pandas as pd

class MyStrategy:
    """自定义策略。"""
    
    def __init__(self, factor_values: pd.DataFrame, close: pd.DataFrame,
                 params: dict = None):
        self.factor_values = factor_values
        self.close = close
        self.params = params or {}
    
    def generate_signals(self) -> pd.DataFrame:
        """生成目标权重信号（日期×标的）。"""
        pass
```

### 8.2 自定义策略示例

```python
import pandas as pd

class MyStrategy:
    """等权买入因子值最高的 top 50 只。"""
    
    def __init__(self, factor_values, close, params=None):
        self.factor_values = factor_values
        self.params = params or {"top_n": 50}
    
    def generate_signals(self):
        top_n = self.params["top_n"]
        ranks = self.factor_values.rank(axis=1, ascending=False)
        weights = pd.DataFrame(0.0, index=self.factor_values.index,
                               columns=self.factor_values.columns)
        weights[ranks <= top_n] = 1.0 / top_n
        return weights
```

> 自定义策略为高级功能，默认使用 FactorQuantileStrategy 即可满足大多数需求。

---

## 9. 完整示例

### 9.1 用户创建因子的完整流程

**Step 1**：在前台点击"新建因子库" → 输入"动量因子"

**Step 2**：在"动量因子"库中点击"新建因子" → 输入"momentum_5d"

**Step 3**：系统弹出模板：

```python
def momentum_5d(self):
    """因子描述"""
    return 
```

**Step 4**：用户填写后：

```python
def momentum_5d(self):
    """5 日动量因子：过去 5 个交易日的收益率。"""
    return self.close.pct_change(5)
```

**Step 5**：前台调用 API 提交回测（只需传函数体，系统自动补全类头）：

```python
import requests

# ResearchEngine API 地址（根据实际部署情况修改）
RE_API = "http://192.168.3.64:9527"

# 只需传函数体，系统自动补全 import 和 class 头
factor_code = """def momentum_5d(self):
    \"\"\"5 日动量因子。\"\"\"
    return self.close.pct_change(5)
"""

response = requests.post(f"{RE_API}/api/backtest/factor", json={
    "factor_code": factor_code,
    "factor_name": "momentum_5d",
    "universe": "CSI500",
    "start": "2020-01-01",
    "end": "2025-12-31",
    "rebalance": "monthly",
    "stock_num": 100,
    "long_short": True,
})

result = response.json()
print(f"夏普率: {result['metrics']['sharpe']:.2f}")
```

---

## 10. 常见问题

### Q1: 因子代码出错怎么办？

因子代码出错不会导致系统崩溃。错误信息会在回测响应中返回：

```json
{
    "metrics": {},
    "error": "因子 momentum 未找到：请检查方法名拼写",
    "meta": null
}
```

常见错误：

| 错误 | 原因 |
|------|------|
| `语法错误: ...` | Python 代码不符合语法规范 |
| `因子 X 未找到` | 因子名拼写错误或方法不存在 |
| `字段 Y 不存在` | 面板中无此字段，用 `self.fields` 查看可用字段 |
| `运行错误: ...` | 因子方法执行时抛出异常 |

### Q2: 如何处理缺失值？

因子值中的 NaN 会被系统自动处理，不需要手动填充。

### Q3: 一个因子库可以写多个因子吗？

**可以**。每次"新建因子"都会在当前库中追加一个方法，所有方法在同一个文件中。

### Q4: 因子参数可以调整吗？

可以。在因子方法中写参数和默认值：

```python
def momentum(self, window=5):  # window 是参数，默认 5
    return self.close.pct_change(window)
```

前台会自动识别参数并允许用户在回测时调整。

### Q5: 如何测试因子是否写对了？

将因子代码通过 `POST /api/backtest` 提交，查看返回的指标和净值曲线。如果 `error` 字段不为空，根据错误信息修正代码。

### Q6: 因子值需要做标准化吗？

不需要。系统内部会对因子值进行排序/分位处理，不会直接使用原始因子值。
