# Product Requirements：WorldQuant Alpha 101 因子库迁移

## 1. 用户故事

1. 作为量化开发者，我希望按 `alpha001`–`alpha101` 使用公开 Alpha 101 公式，以便复现实验。
2. 作为研究员，我希望通过索引看到因子库名称、公式来源和字段依赖，以便判断数据口径。
3. 作为平台维护者，我希望旧版 `alpha_library` 继续可加载，以便已有示例和请求不被破坏。

## 2. 业务流程

```text
FactorLoader.load("worldquant_alpha101")
        ↓
枚举 alpha001–alpha101
        ↓
Panel（OHLCV + 可选 amount/vwap/市值/行业）
        ↓
FactorEngine / ResearchEngine
        ↓
因子分析、分层回测或内置因子回测 API
```

## 3. 业务规则与边界

- 新库名为 `worldquant_alpha101`，方法名为三位补零的 `alpha001`–`alpha101`。
- `adv{n}` 优先使用 `amount` 的滚动均值；无 `amount` 时使用 `close × volume` 的滚动均值。
- `vwap` 优先使用面板 `vwap`，其次使用 `amount / volume`，最后使用典型价格 `(high + low + close) / 3`。
- `cap` 优先使用 `cap` 或 `total_mv`；缺失时仅以 `close × volume` 作为无市值样本的近似值，生产研究应提供真实市值字段。
- `indneutralize` 优先使用对应的 `sector`、`industry` 或 `subindustry` 字段；缺失时退化为截面去均值，结果不得标记为同源逐值验证。
- 所有时间序列窗口按论文规则 floor 为整数，只读取当前及历史行。
- 旧 `alpha_library.py` 保持现有方法和名称，不与新库合并。

## 4. 非功能要求

- 不新增 WorldQuant、聚宽或其他第三方运行时依赖。
- 每个因子返回与输入一致的日期×标的 `DataFrame`。
- 101 个因子均能在包含 OHLCV、amount、市值和行业分类的标准测试面板上执行。
- API 仅通过已登记的内置库白名单加载，不执行用户指定模块。

## 5. 可测试验收标准

1. `FactorLoader.load("worldquant_alpha101")` 注册恰好 101 个因子，首尾名称为 `alpha001`、`alpha101`。
2. Alpha 41、Alpha 101 等代表公式与确定性参考计算一致。
3. 全部 101 个因子在标准面板上返回相同形状和索引列。
4. 改变最后一行数据不会改变此前日期的因子值。
5. 缺少 `amount` 时 VWAP 回退到典型价格仍可运行；具体数据口径在索引和技术设计中可追溯。
6. `/api/factors` 可以发现 `alpha001` 和 `alpha101`，内置白名单包含 `worldquant_alpha101`。
