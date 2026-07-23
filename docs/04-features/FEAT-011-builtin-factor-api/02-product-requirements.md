# Product Requirements：内置因子库回测 API

## 规则

- 未提供 `factor_code` 时，必须提供单个 `library_name`；服务端加载完整库后按 `factor_name` 取因子。
- 提供 `factor_code` 时，用户只提交一个因子函数，服务端生成 `FactorLibrary` 模板；可选传一个或多个 `library_name`，使函数直接调用相应内置因子方法。
- `library_name` 仅能是服务端登记的内置库；多库组合的因子方法名不得重名。
- 未提供来源，或直接执行内置因子时传多个库名，返回 HTTP 422。

## 验收

1. `jq_compat_risk` 中依赖 `_returns` 的 `jq_kurtosis60` 可只凭库名和因子名完成回测。
2. 自定义 `combo_factor` 可在同一函数内调用 `self.jq_kurtosis20()` 与 `self.qlib_alpha158_kmid()` 并成功回测。
3. 现有单函数自定义因子请求保持成功；未登记库名、未知因子名返回可读业务错误，不能导入任意模块。
