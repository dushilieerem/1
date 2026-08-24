# Technical Design：国泰君安 Alpha191 因子库迁移

## 模块边界

```text
Factor/libraries/gtja_alpha191.py
  └─ GTJAAlpha191Library（FactorLibrary）
       ├─ alpha191_001 … alpha191_191
       └─ Panel 算子与字段回退
ResearchEngine FactorLoader / factor_catalog
  └─ 从 index.yaml 发现并适配方法
ResearchEngine API
  └─ 按库名加载单个 Alpha191 因子
```

QuantCore 的 Panel 和 FactorLibrary 契约不改动；新公式库独立于现有 WorldQuant、Qlib
和技术指标库，避免共享基类的高风险变更。

## 算子与计算口径

- 截面：`RANK` 使用按日期的百分位排名。
- 时序：`SUM`、`MEAN`、`STD`、`MIN/MAX`、`TSRANK`、`LOWDAY/HIGHDAY` 使用按标的滚动窗口。
- 关系：`CORR`、`COV` 使用 Pandas rolling 统计；无穷值转缺失。
- 平滑：`SMA(X,N,M)` 使用 `ewm(alpha=M/N, adjust=False)`。
- 衰减：`DECAYLINEAR` 使用当前观测权重最高的线性权重。
- 回归：`REGBETA` 对确定性序列使用闭式斜率；过滤基准日时按有效配对样本滚动回归。

## 数据契约

| 字段 | 级别 | 用途 |
|---|---|---|
| `open/high/low/close/volume` | 必须 | 191 条公式的基础行情 |
| `amount` | 可选 | 资金流和成交额类公式；缺失时 `close * volume` |
| `vwap` | 可选 | VWAP 公式；缺失时 amount/volume，再退化为典型价格 |
| `benchmark_close/open` | 可选 | Alpha075/149/181/182；缺失时 CSI300 或等权市场代理 |

## 兼容、回滚与接口影响

- 新库在 `index.yaml` 登记为 `gtja_alpha191`，不复用 `alpha001` 等 WorldQuant 名称。
- 发生问题时从 `index.yaml` 移除 `gtja_alpha191` 即可停止 API 发现；其他库不受影响。
- 新增方法通过动态注册保持编号完整，但源码方法事实来源仍为同一模块的公式映射。

## 关键风险

1. 供应商复权、VWAP、成交额和交易日历口径差异会导致逐值偏差。
2. Alpha149 等基准过滤公式在缺少同源指数时只能使用等权代理。
3. 191 个因子中部分窗口很长，真实全市场计算应依赖 ADR-018 的完整历史预热语义。
