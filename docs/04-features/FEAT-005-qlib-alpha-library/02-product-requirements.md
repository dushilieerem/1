# Product Requirements：Qlib Alpha 特征库

## 用户故事

作为量化开发者，我希望在 SVQuant 中看到并计算 Qlib Alpha158 / Alpha360 特征，以便复用公开研究基线。

## 业务规则与边界

- 特征以 `qlib_alpha158_`、`qlib_alpha360_` 为前缀，尾部为 Qlib 原始特征名的小写形式。
- Alpha158 包含 9 个 K 线特征、4 个当日价格特征和 29 类滚动特征 × 5 个窗口，共 158 个。
- Alpha360 包含 close/open/high/low/vwap/volume 各 60 个滞后特征，共 360 个。
- VWAP 优先读取 `vwap` 字段；不存在时使用 `amount / volume` 推导。
- 仍遵守 Qlib 的历史窗口定义；不使用未来数据。

## 非功能要求与验收

- 不新增 Qlib 依赖。
- 因子加载器可注册 518 个特征；`GET /api/factors` 可枚举内置 Alpha 与 Qlib Alpha 特征。
- 代表性 K 线、滞后价格、VWAP 和滚动特征须通过确定性公式测试。
