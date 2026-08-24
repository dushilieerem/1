# 自定义证券池与组合基准：技术设计

## 模块边界

WebApp 负责用户资产持久化、版本、CRUD 与权限；`ResearchEngine` 负责校验已解析快照并把它传给现有编排；`QuantCore` 只接收已解析的证券集合或收益序列，不感知用户、数据库和权限。

```text
WebApp 用户资产 CRUD / 鉴权 / 数据库                WebApp 用户资产 CRUD / 鉴权 / 数据库
                         │                                      │
                         └────── 解析为不可变 Snapshot ────────┘
                                           │ AssetSnapshot
                         ┌─────────────────┴─────────────────┐
                         ▼                                   ▼
              resolve_universe / 面板过滤          PassiveBenchmarkCalculator
                         │                                   │
                         └────── ResearchEngine 回测编排 ────┘
                                           │
                           BacktestResult / API meta / 结果存储
```

## WebApp → ResearchEngine 快照契约

WebApp 对用户资产完成鉴权和版本解析后，将完整不可变快照传给 ResearchEngine。证券池为 `{asset_id, version, content_hash, symbols, membership_mode: "static"}`；基准为 `{asset_id, version, content_hash, weights, pricing: "close_to_close"}`。MVP 不接受隐式等权；WebApp 必须写出已归一化权重。

## 核心对象与接口

```python
@dataclass(frozen=True)
class UniverseSnapshot:
    asset_id: str
    version: str
    content_hash: str
    symbols: tuple[str, ...]

@dataclass(frozen=True)
class BenchmarkSnapshot:
    asset_id: str
    version: str
    content_hash: str
    weights: pd.Series  # index=symbol, sum=1
    pricing: Literal["close_to_close"]

class WebAppAssetResolver:
    def resolve_universe_for_user(...) -> UniverseSnapshot: ...
    def resolve_benchmark_for_user(...) -> BenchmarkSnapshot: ...
```

API 的 `universe_snapshot`、`benchmark_snapshot` 为 WebApp 已解析的完整快照。响应 `meta` 新增可选 `universe_asset`、`benchmark_asset`；为避免响应过大，只返回摘要，完整快照写入回测结果的配置/元数据文件。ResearchEngine 不提供资产列表或 CRUD API。

## 运行时设计

1. Runner 在读取行情前解析证券池；将 `symbols` 与 `close` 面板列求校验后的交集。发现任何不存在的代码即失败，而非静默取交集。
2. 因子回测和向量化策略回测均将解析后的 symbols 传给现有 `resolve_universe` 后续的面板过滤路径；这保证研究截面与策略数据一致。
3. Runner 读取基准全部成分的收盘价，以首个共同有效日为起点，计算 `returns = close.pct_change()` 与 `portfolio_return = returns.dot(weights)`，再累计为净值。不得把价格直接按权重相加。
4. 回测启动前建立 `ResolvedResearchContext`，其中包含资产快照、数据版本标识和日期范围；运行期间只使用该不可变对象。
5. 未使用资产引用的旧请求继续走 `_load_benchmark_equity` 与内置 `universe` 解析，避免改动已有接口语义。

## 数据与兼容影响

- 不改动 `FieldParquetProvider` 的固定指数读取契约；自定义资产由 WebApp 解析为快照后传入。
- 不把“最新一期指数成分”升级为历史池。历史 `日期×标的` 成分掩码、指数调仓和幸存者偏差修复作为后续 Feature，需扩展数据目录与 `UniverseSnapshot` 的时间序列表示。
- 不新增数据库表；Wave 3 可将 Catalog 的存储适配器替换为用户资产服务，保持 `AssetRef → Snapshot` 契约不变。

## 测试策略

- ResearchEngine 快照契约单测：重复证券、无效权重、缺失价格与旧参数互斥。
- `PassiveBenchmarkCalculator` 单测：固定权重收益、首日归一化、缺失价与无重叠日期。
- Runner/API 集成测试：因子和策略各覆盖一次自定义证券池；自定义基准净值、元数据快照、旧枚举参数回归。
- 以小型确定性行情夹具手算基准收益，禁止仅断言“返回非空”。

## 回滚与风险

Feature 以新增目录、Catalog 和可选请求字段实现。回滚时停止传入 `*_ref` 并保留既有内置路径；已保存结果仍含其资产快照。主要风险是把静态股票清单宣传成历史指数池，文档与 API 元数据必须标明 `membership_mode: static`，并在后续历史成分能力上线前拒绝此类表述。
