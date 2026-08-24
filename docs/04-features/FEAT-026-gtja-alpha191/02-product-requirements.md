# Product Requirements：国泰君安 Alpha191 因子库迁移

## 用户故事

1. 作为量化开发者，我希望按 `gtja_alpha191` 加载 191 个稳定编号的因子，以便迁移已有研究。
2. 作为研究员，我希望看到每个因子的字段依赖、预热窗口和来源，以便判断是否可用于回测。
3. 作为平台维护者，我希望缺少 amount、VWAP 或基准时有明确且可追溯的降级口径。

## 业务流程

```text
FactorLoader.load("gtja_alpha191")
        ↓
枚举 alpha191_001 … alpha191_191
        ↓
OHLCV + 可选 amount/VWAP/benchmark 面板
        ↓
向量化计算 → 因子分析 / 分层回测 / API
```

## 业务规则与边界

- 因子名固定为 `alpha191_NNN`，库名固定为 `gtja_alpha191`。
- 必需字段：`open`、`high`、`low`、`close`、`volume`。
- amount 缺失时使用 `close * volume`；VWAP 依次回退到 amount/volume 和典型价格。
- 基准优先使用 `benchmark_close`/`benchmark_open` 或 CSI300；缺失时使用等权市场代理并
  在文档中声明。
- Alpha030 因缺少 Fama-French 市场因子返回全缺失值，但仍登记为可发现编号。
- 所有因子返回输入日期×标的宽表；除零、无穷和不完整滚动窗口保留为缺失值。

## 非功能要求

- 不新增第三方运行时依赖；仅使用 Pandas、NumPy 和现有 FactorLibrary。
- 计算只读取当前及历史数据，不使用负向 shift 或未来行。
- 因子目录唯一来源为 `Factor/libraries/index.yaml`，由 `factor_catalog sync/check` 维护。

## 可测试验收标准

1. 加载库后恰好发现 191 个方法，首尾为 `alpha191_001`、`alpha191_191`。
2. Alpha001、Alpha002、Alpha041 与确定性手算公式一致。
3. 191 个方法在标准 OHLCV 面板上均返回相同形状、索引和列。
4. 移除 amount/VWAP 后，VWAP 相关因子按回退规则仍可运行。
5. 修改最后一行行情不影响此前日期的 Alpha001、Alpha041、Alpha149、Alpha191。
6. 索引、总览文档和源码数量分别为 1043、1043、191/191。
