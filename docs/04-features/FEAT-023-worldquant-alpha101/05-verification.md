# Verification：WorldQuant Alpha 101 因子库迁移

## 自动化验证

- `FactorLoader.load("worldquant_alpha101")` 注册 101 个方法因子。
- `alpha041` 与 `alpha101` 通过确定性公式对照。
- 101 个因子在含 OHLCV、amount、市值和行业字段的标准面板上全部返回日期×标的宽表。
- 改变最后一行数据后，Alpha 1、41、58、101 的历史输出保持不变。
- 缺少 `amount` 时，VWAP 相关公式按约定回退到典型价格。
- `/api/factors` 可发现 `alpha001`、`alpha101`；内置回测白名单包含 `worldquant_alpha101`。

## 执行命令

```bash
conda run --no-capture-output -n svquant python -m pytest ResearchEngine/tests/test_worldquant_alpha101.py -q
```

## 未覆盖项

当前状态为 `implemented`，尚未取得与本项目数据源完全同源的参考因子值，因此不宣称与第三方平台逐值一致。行业分类、复权和成交额口径应在数据底座稳定后补充回归样本。
