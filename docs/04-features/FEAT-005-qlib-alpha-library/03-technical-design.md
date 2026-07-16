# Technical Design：Qlib Alpha 特征库

## 模块边界

```text
Factor/libraries/qlib_alpha.py
  └─ QlibAlphaLibrary（FactorLibrary）
       ├─ Alpha158：158 个方法因子
       └─ Alpha360：360 个方法因子
ResearchEngine FactorLoader / GET /api/factors
  └─ 加载并枚举上述因子
```

实现仅依赖 Pandas/NumPy，复刻 Microsoft Qlib `Alpha158DL`、`Alpha360DL` 的公式；不引入 Qlib 数据处理器、标签或模型组件。

## 数据与兼容

依赖 `open`、`high`、`low`、`close`、`volume` 和 `vwap` 或可推导它的 `amount`。缺少以上字段时由现有 Panel 的字段访问机制明确报错，不静默填充。新库不修改既有因子名称或行为；删除 `qlib_alpha.py` 并移除索引项即可回滚。

## 风险与缓解

部分滚动回归特征计算成本高。它们按需计算且沿用现有懒加载、单因子执行模型；后续如出现性能瓶颈，再针对热点因子优化，不预先引入额外抽象。
