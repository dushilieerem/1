# FEAT-004：因子资产目录与回测结果缓存 — Verification

- 验证日期：2026-07-17
- 状态：通过

## 验证结果

| 验证项 | 结果 | 证据 |
|--------|------|------|
| 因子资产迁移 | 通过 | 因子库已迁移至 `Factor/libraries/`；`GET /api/factor-libraries` 返回因子库目录，`GET /api/factors/alpha_library` 返回该库的 5 个内置因子。 |
| 首次回测缓存 | 通过 | API 测试断言响应头为 `X-SVQuant-Cache: MISS`。 |
| 重复回测缓存 | 通过 | 相同请求第二次调用返回 `X-SVQuant-Cache: HIT`，响应体一致。 |
| 数据变更失效 | 通过 | 更新行情 Parquet 文件修改时间后，相同请求重新返回 `MISS`。 |
| 已移除参数校验 | 通过 | 因子 API 测试覆盖旧字段，返回 HTTP 422。 |
| 全量回归 | 通过 | `pytest -q`：92 passed。 |

## 交付说明

- `Factor/backtest_results/` 已加入 `.gitignore`，属于可自动清理的运行时缓存。
- 可通过 `SVQUANT_FACTOR_DIR`、`SVQUANT_BACKTEST_CACHE_DIR`、
  `SVQUANT_BACKTEST_CACHE_ENABLED`、`SVQUANT_BACKTEST_CACHE_TTL_DAYS` 和
  `SVQUANT_BACKTEST_CACHE_MAX_BYTES` 调整部署行为。
- 遗留的 `ResearchEngine/factor/__pycache__/` 为本地 Python 缓存，不纳入版本控制；因子源码已迁出。
