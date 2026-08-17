# Verification：国泰君安 Alpha191 因子库迁移

## 自动化验证

状态：已完成（2026-08-14）。

- `FactorLoader.load("gtja_alpha191")` 发现 191 个方法，首尾名称正确。
- Alpha001、Alpha002、Alpha041 通过确定性公式对照。
- 全部 191 个方法在含 OHLCV、amount 的标准面板上返回日期×标的宽表。
- 缺少 amount/VWAP 时，VWAP 相关公式使用约定回退。
- 修改最后一行行情不影响此前日期的代表性因子值。
- `factor_catalog check` 验证源码、索引和数量一致。

## 执行命令

```powershell
conda run --no-capture-output -n svquant python -m pytest ResearchEngine/tests/test_gtja_alpha191.py -q
conda run --no-capture-output -n svquant python -m researchengine.factor_catalog check
```

## 未覆盖项

尚未取得与本项目数据源完全同源的 Alpha191 因子值，因此只声明公式复算与工程契约
验证，不声明第三方平台逐值一致或任何收益有效性。Alpha030 的 Fama-French 依赖和
基准代理口径需要在数据底座补齐后单独回归。
