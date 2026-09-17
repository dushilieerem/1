# 数据存储设计

> 本文档定义 SVQuant 的数据存储方案。
> 关联：`system_architecture.md`、`../01-需求文档/产品定位.md`、`../../ResearchEngine/docs/02-架构文档/researchengine_architecture.md`

> 当前基线：`marketdata/` 以 iFinD 目录镜像形式提供只读数据，ResearchEngine 通过
> `FieldParquetProvider → DataEngine` 只读访问；因子回测由
> `BacktestEngine` 组织，批量指标使用独立 `FactorBacktestStore` SQLite。本文描述项目级数据
> 所有权和物理布局，模块内的运行时细节以 ResearchEngine 架构文档和 ADR-018/020/022 为准。

---

## 1. 数据概览

SVQuant 涉及以下几类数据：

| 数据类别 | 数据量级 | 实时性要求 | 存储格式 |
|---------|---------|-----------|---------|
| 行情日线 | 5000 标的 × 2000+ 日 ≈ 1000 万行 | 低（历史数据） | Parquet |
| 分钟数据 | 5000 标的 × 240 分钟 × 250 日/年 ≈ 3 亿行/年 | 中 | Parquet |
| 基本面数据 | 5000 标的 × 季度 ≈ 2 万行/年 | 低 | Parquet |
| 因子值 | 5000 标的 × 2000+ 日 × N 因子 | 低（运行时） | numpy array（内存） |
| 回测结果 | 每次回测 ≈ 数千行 | 低 | CSV / Parquet / SQLite |
| 用户数据 | 用户数 × 配置项 | 低 | YAML |
| 政策事件 | 数百-数千条/年 | 中 | Parquet / SQLite |

---

## 2. 存储方案选择

### 2.1 为什么选择 Parquet？

| 方案 | 优点 | 缺点 |
|------|------|------|
| **Parquet ✅** | 列式存储、压缩率高、查询快、Python 生态支持好 | 不支持随机写入 |
| CSV | 人类可读、通用 | 大文件慢、无压缩、无 schema |
| SQLite | 支持 SQL 查询、事务 | 大表性能差、不适合分析场景 |
| ClickHouse | 极速分析查询、列式存储 | 需要部署服务、运维成本 |

**决策**：历史行情和基本面数据使用 **Parquet** 持久化，发布物可按业务域组织为多字段宽表，
也兼容按逻辑字段拆分的 Parquet 文件；`FieldParquetProvider` 对上统一提供“日期 × 标的”的
字段面板。因子值默认只在每个任务运行时以内存数组存在；需要长期保存时可导出 Parquet。
完整回测结果可选 CSV / Parquet / SQLite / ClickHouse，批量历史和标量指标单独使用 SQLite。

### 2.2 给老板的解释

**Parquet 比 CSV 好在哪？**

CSV 存股票数据，要查"所有股票某一天的收盘价"需要读整个文件。Parquet 只读需要的列，速度快 10-100 倍，而且文件体积只有 CSV 的 1/3。

**为什么不用数据库？**
因为量化的分析场景（算 IC、回测）需要把所有数据加载到内存做矩阵运算，数据库的查询接口反而成为瓶颈。Parquet 作为文件格式，加载快、生态好、无需部署。

---

## 3. 数据目录结构

```text
SVQuant/marketdata/
├── market_data/
│   └── market_data_hfq.parquet      # 后复权行情和流动性
├── unadjusted_price/
│   └── unadjusted_price.parquet     # WebApp 未复权 K 线
├── date_sequence/
│   └── date_sequence.parquet        # 估值、行业与证券状态
├── index/
│   ├── index_price/
│   │   └── index_price_<index>.parquet
│   └── index_weights/
│       └── index_weights_<index>.parquet
├── universe/
│   └── a_share.parquet              # 静态全 A 股票池
├── calendar/
│   └── calendar_all_a.parquet
├── data_manifest.yaml
└── quality_report.json
```

`marketdata/` 是当前 ResearchEngine 实际消费的数据根目录；旧 `MarketData/` 目录已废弃，仅保留迁移提示。
活动数据只读；候选生成、历史 release、质量校验和备份均在独立 IFind 项目完成，发布阶段把验证通过的目录镜像同步到 `marketdata/`。
ResearchEngine 在运行时计算 release signature；release 切换后，新任务使用新上下文，正在运行的任务
继续持有原只读上下文。

ResearchEngine 的数据 Provider 当前优先消费 iFinD 的目录镜像布局：

- 业务域宽表：`market_data/market_data_hfq.parquet`、`date_sequence/date_sequence.parquet`；
- 指数价格与权重：`index/index_price/`、`index/index_weights/`；
- 展示行情与股票主数据：`unadjusted_price/`、`universe/a_share.parquet`；
- 旧版 `panels/`、`benchmark/` 以及单字段 Parquet 仅作为测试和迁移期兼容格式保留。

两种布局都必须通过 `IDataProvider` / `FieldParquetProvider` 转换为统一字段面板，业务 services
不得直接依赖具体文件名或 Parquet 物理布局。

### 运行时领域模型

物理文件按业务域分组后，ResearchEngine 也按相同业务边界表达运行时数据：

```text
MarketDataRelease
├── stock: StockDailyData            # market_data/market_data_hfq.parquet
├── basic: DailyBasicData            # date_sequence/date_sequence.parquet
└── status: SecurityStatusData       # date_sequence/date_sequence.parquet
```

`open`、`close`、`pb_mrq`、`up_and_down_status` 等逻辑字段在这些对象上仍是原生
`DataFrame[日期 × 证券]`，而不是字段名字符串或 Pandas 包装类。例如
`release.stock.close` 就是后复权收盘价 DataFrame。`ResearchDataPanel` 是服务层的
计算视图，同时允许因子表达式继续使用 `data.close`，并提供 `data.stock.close`、
`data.basic.pb_mrq`、`data.status.up_and_down_status` 等显式业务域访问。旧 `models.data.Panel`
在迁移期保持兼容，待因子和策略调用方都完成迁移后再删除。

### 为什么按业务域组织多字段宽表？

1. **贴合发布与读取模式**：价格和流动性、估值和股本等相关字段通常成组发布，Provider 再按字段读取。
2. **减少资产碎片**：日期轴和证券轴不必在每个字段文件中重复维护，发布与校验以业务资产为单位。
3. **保持职责隔离**：研究行情、日频基本面、证券状态和展示价格分别更新，不形成一张难以治理的总表。
4. **不牺牲字段接口**：Provider 仍按字段返回“日期 × 证券”面板，服务器内存仍按字段保存只读二维数组；
   物理布局变化不向上泄漏。

股票日频多字段宽表使用 `(symbol, field)` 两级列。当前 `date_sequence` 的 iFinD 原始字段在
`FieldParquetProvider` 边界去掉 `ths_` 前缀和 `_stock` 后缀后暴露为逻辑字段；当前版本不提供
独立的 `is_suspended` 字段，停牌过滤在字段缺失时按放行处理，涨跌停从
`up_and_down_status` 原始文本判断。

---

## 4. 因子值存储（运行时）

因子值不在 Parquet 中持久化（可缓存但不强制），而是在运行时以 numpy array 管理：

```
因子值 = DataEngine 加载行情 → FactorEngine.compute() → numpy array
```

| 维度 | 说明 |
|------|------|
| 形状 | (N_dates, N_stocks) |
| 类型 | float64 / float32 |
| 内存 | 5000 × 2000 × 8 bytes ≈ 80 MB / 因子 |
| 生命周期 | 运行时持有，进程结束后释放 |

对于需要长期保存的因子值，用户可选择导出到 Parquet。

---

## 5. 回测结果存储

```
ResearchEngine/output/
├── experiments/
│   ├── 20260715_alpha101_001/
│   │   ├── config.yaml              # 回测配置
│   │   ├── nav.csv                  # 净值曲线
│   │   ├── holdings.csv             # 每日持仓
│   │   ├── trades.csv               # 成交记录
│   │   ├── metrics.json             # 绩效指标
│   │   └── reports/                 # 报告文件
│   └── ...
```

可选的存储后端（通过配置切换）：

| 后端 | 适用场景 | 配置 |
|------|---------|------|
| CSV | 小规模、人类可读；应用未指定时的兼容默认 | `storage: csv` |
| Parquet | 大批量结果 | `storage: parquet` |
| SQLite | 需要 SQL 查询 | `storage: sqlite` |
| ClickHouse | 生产环境/大规模 | `storage: clickhouse` |

完整结果存储与批量指标存储是两条不同的数据边界：完整净值、持仓、成交和报告由
`ResultManager`/`ResultStorage` 管理；批量协调器只把批次状态、因子运行状态和标量指标投影到
独立的 `FactorBacktestStore`，默认数据库为 `Factor/database/factor_backtest.db`。批量 Store
不保存完整净值曲线，也不替代通用结果存储。

文件缓存属于可再生加速层，不是业务历史或审计记录。因子缓存键至少绑定规范化请求、因子源码哈希、
MarketData release、执行版本和指标版本；当前文件缓存版本为 `factor-backtest-v10`。

---

## 6. 数据流

```
外部数据源（iFinD / AKShare / CSV）
       ↓
  独立 IFind 项目或其他数据接入任务采集并构建候选 release
       ↓
  按业务域宽表或字段文件发布为不可变 release
       ↓
  FieldParquetProvider / DataEngine（统一字段接口）
       ↓
  FastAPI lifespan → DataEngine（按固定 release 复用的只读快照）
       ↓
  BacktestEngine
       ├─ DataEngine → FactorEngine → PortfolioEngine → MetricEngine
       └─ 因子值/组合/指标中间结果（任务私有）
       ↓
  ResultManager / ResultStorage → output/（完整结果）
  FactorBacktestStore → Factor/database/factor_backtest.db（批量标量历史）
```

因子任务只读取 `start/end` 指定范围内的可用行情；数据源在截止日无数据时返回实际最后
交易日。滚动窗口不足产生的缺失值属于因子定义的结果，不由系统补读区间前历史。

---

## 7. 相关决策

- `../05-技术决策/ADR-001-为什么使用向量化回测.md` — 向量化回测优先，Parquet 的列式读取对向量化计算友好
- `../05-技术决策/ADR-003-为什么行情数据采用文件存储并选择Parquet.md` — 历史行情为何采用文件存储，以及为何以 Parquet 为标准格式
- `../05-技术决策/ADR-016-Parquet持久化与只读内存快照.md` — 持久化版本与回测运行时内存快照的职责划分
- `../05-技术决策/ADR-017-市场数据按业务域采用多字段宽表.md` — 股票日频数据的业务域多字段物理布局
- [ADR-028：因子回测由 BacktestEngine 编排四引擎](../05-技术决策/ADR-028-因子回测由BacktestEngine编排四引擎.md) — 因子回测的引擎职责及日期范围
- `../../ResearchEngine/docs/05-技术决策/ADR-020-因子批量指标仓库使用独立SQLite.md` — 批量指标仓库边界
- [ADR-030：DataEngine 持有应用级市场数据快照](../05-技术决策/ADR-030-DataEngine持有应用级市场数据快照.md) — release 级快照与字段缓存
- [ADR-031：iFinD 采集迁移为独立项目](../05-技术决策/ADR-031-iFinD采集迁移为独立项目.md) — 供应商采集、凭据、源数据和发布工具的仓库边界
- `system_architecture.md` — 架构总览中的数据层
