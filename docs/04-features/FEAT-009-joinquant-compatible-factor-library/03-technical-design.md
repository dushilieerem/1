# Technical Design：聚宽兼容因子库

## 模块边界

```text
授权数据源 / 目录快照（离线输入，不进入运行时）
              ↓
Factor/libraries/index.yaml
              ├─ 目录、别名、字段依赖、状态与验证证据
              └─ 后续补充 snapshots/<version>.json（仅元数据）
              ↓
Factor/libraries/jq_compat_<category>.py
              └─ FactorLibrary 子类（原生 Pandas/NumPy 向量化公式）
              ↓
QuantCore Panel / DataEngine
              ↓
ResearchEngine FactorLoader → index/API → 因子分析与回测
```

实现落在项目级 `Factor/libraries/`，不放入 `ResearchEngine`；`QuantCore` 负责通用面板字段访问与数据契约，`ResearchEngine` 仅负责加载、执行和返回结果。目录管理、授权凭据和用户因子资产属于未来应用层，不由 ResearchEngine 管理。

## 清单与命名

以 `jq_compat_<分类>.py` 按目录分类拆分，每个文件一个 `FactorLibrary` 子类。第一批已使用 `jq_compat_technical.py`；方法名为 `jq_<source_name.lower()>`，例如 `jq_earnings_to_price_ratio`。如果原始名不符合 Python 标识符，由导入工具生成稳定转写，并在 `Factor/libraries/index.yaml` 保留原始名。

`index.yaml` 中兼容条目的最小记录：

```yaml
- source_name: earnings_to_price_ratio
  svquant_name: jq_earnings_to_price_ratio
  category: valuation
  status: verified
  required_fields: [net_profit_ttm, total_mv]
  availability_rule: point_in_time_financials
  formula_reference: "净利润 TTM / 总市值"
  source_snapshot: jq-factor-catalog-YYYY-MM-DD
  implementation: jq_compat_valuation.JQValuationLibrary.jq_earnings_to_price_ratio
  verification: fixtures/jq_compat/earnings_to_price_ratio.json
```

`index.yaml` 只汇总可运行项，展示原始名称、中文名、类别、状态及 manifest 版本，避免手工维护两份可运行清单。

## 数据契约与映射

| 类别 | 最低字段/能力 | 现状 | MVP 策略 |
|---|---|---|---|
| 技术、动量、风险 | OHLCV、复权与交易日历 | 基本具备 | 首批实现并验证。 |
| 估值、市值 | 总/流通市值、PE/PB/PS、TTM 财务字段 | 部分具备 | 先核对字段含义和单位，再实现。 |
| 成长、质量、每股 | 按公告日对齐的单季/TTM财务报表、股本 | 未形成统一点时契约 | 新增财务 provider 和字段字典后实施。 |
| 风格、行业 | 行业分类历史版本、基准指数/风险暴露 | 不完整 | 延后，先定义分类版本和中性化规则。 |
| 情绪、预期、资金流 | 分析师预测、机构覆盖、北向/资金流等 | 未接入 | 依赖授权数据后实施。 |

新增财务字段必须采用 `field × 日期 × 标的` 面板：源记录保存报告期、公告日、修订版与来源版本；供因子使用的日频面板仅在公告/可见日及之后前向填充。所有价格类公式统一明确前复权/后复权/不复权；与参考样本对比时必须使用同一口径。

## 导入与验证工具

导入工具只接受用户本地、合法导出的 `get_all_factors()` 元数据文件，生成规范化快照、哈希和 manifest 草稿；它不访问聚宽网络、不保存凭据、不下载因子数值。实现者补齐字段映射与公式后，再由校验工具检查：名称唯一性、依赖字段存在性、方法签名、输出形状、未来数据、固定夹具公式以及可选的参考样本容差。

## 兼容、回滚与测试

- 现有因子库、名称和 API 保持不变；兼容库独立加载，发生问题可从 `index.yaml` 移除该库而不影响既有因子。
- manifest 和目录快照均版本化；新目录版本作为新增版本发布，不覆盖过去的映射证据。
- 测试分为：目录/命名校验、字段缺失、确定性公式、公告日点时性、向量化输出、参考样本回归与全量加载回归。

## 关键技术风险

最大风险不在公式编码，而在原始目录是否完整、字段定义是否可得、复权/财务可见日与参考平台是否一致。没有经过回归验证的实现必须显式标记，不得以“兼容”名义承诺数值一致。
