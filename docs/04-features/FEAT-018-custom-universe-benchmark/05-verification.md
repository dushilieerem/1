# FEAT-018 验证记录

- 验证日期：2026-07-31
- 状态：待验收

## 自动化验证

执行：

```bash
conda run -n svquant python -m pytest \
  ResearchEngine/tests/test_research_assets_api.py \
  ResearchEngine/tests/test_api.py -q
```

结果：ResearchEngine 相关测试 52 passed；当前全量回归为 190 passed。均仅有 1 个来自 FastAPI 测试客户端依赖的弃用警告。

## 验收映射

| 验收标准 | 证据 |
|---|---|
| AC-1 | WebApp 负责资产 CRUD、列表与权限；ResearchEngine 不提供列表端点。本仓库研究模块仅完成其快照消费契约，WebApp CRUD 验收待 WebApp 交付。 |
| AC-2 | `test_factor_backtest_uses_webapp_resolved_snapshots` 以两证券静态快照运行因子回测并返回资产摘要。 |
| AC-3 | `test_vectorized_strategy_uses_assets_and_rejects_mixed_source` 以同一静态池运行向量化策略。 |
| AC-4 | `test_passive_benchmark_matches_manual_fixed_weight_return` 和 API 手算净值断言。 |
| AC-5 | 因子与策略响应 `meta` 返回版本、哈希和成分数量；`ResultManager.meta` 保存完整快照。 |
| AC-6 | 目录重复证券、非归一化权重、混用旧/新参数和缺失价格均有自动化校验。 |
| AC-7 | `ResearchEngine/tests/test_api.py` 全部通过。 |

## 已知限制与回滚

- 仅支持静态 A 股代码清单和固定非负权重的收盘到收盘基准；不支持历史成分、自动调仓、动态规则或事件驱动策略引用。
- 回滚时停止传入 `universe_snapshot`、`benchmark_snapshot`，即可继续使用已有固定指数参数；已保存结果保留其解析快照。
