# Verification：Qlib Alpha 特征库

- 已验证：`QlibAlphaLibrary` 注册 518 个方法因子（Alpha158 158 个、Alpha360 360 个）。
- 已验证：`KMID`、`CLOSE5`、`ROC5` 与 VWAP 回退公式的确定性测试。
- 已验证：不需要安装 Qlib；测试仅使用项目既有的 Pandas/NumPy 依赖。
- 回归：执行 `pytest ResearchEngine/tests/test_qlib_alpha.py -q`。
