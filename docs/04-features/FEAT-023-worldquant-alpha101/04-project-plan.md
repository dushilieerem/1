# Project Plan：WorldQuant Alpha 101 因子库迁移

| 任务 | 复杂度 | 风险 | 依赖 | 完成条件 |
|---|---:|---|---|---|
| 统一 Alpha 101 算子与字段回退 | 3 | 中 | Panel / Pandas | 算子可复用且不读未来数据 |
| 实现 alpha001–alpha101 | 4 | 中 | 公式来源、OHLCV | 101 个方法可被 FactorLoader 注册 |
| 接入索引与内置 API 注册 | 2 | 低 | FactorLoader / runner | 库名和因子名可发现、可调用；唯一来源为 `Factor/libraries/index.yaml` |
| 确定性与全量执行测试 | 3 | 中 | 上述任务 | 定向测试全部通过 |
| 文档与验收记录 | 2 | 低 | 测试结果 | README、索引、Verification 同步 |

## 排期与里程碑

- M1：公式、字段契约和命名确定。
- M2：101 个因子和加载链路完成。
- M3：公式、形状、无未来数据测试通过并完成交付记录。

## 回滚方案

从 `index.yaml` 移除 `worldquant_alpha101` 条目即可停止新库发现；不删除旧 `alpha_library` 或其他因子文件。
