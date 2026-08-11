# 数据存储设计

> 本文档定义 SVQuant 的数据存储方案。
> 关联：`system_architecture.md`、`../02-product/产品定位.md`

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

**决策**：历史行情和基本面数据使用 **Parquet** 持久化，股票日频数据按业务域组织为多字段宽表。因子值默认只在运行时以内存数组存在；需要长期保存时可导出 Parquet。回测结果可选 CSV / Parquet / SQLite / ClickHouse。

### 2.2 给老板的解释

**Parquet 比 CSV 好在哪？**

CSV 存股票数据，要查"所有股票某一天的收盘价"需要读整个文件。Parquet 只读需要的列，速度快 10-100 倍，而且文件体积只有 CSV 的 1/3。

**为什么不用数据库？**
因为量化的分析场景（算 IC、回测）需要把所有数据加载到内存做矩阵运算，数据库的查询接口反而成为瓶颈。Parquet 作为文件格式，加载快、生态好、无需部署。

---

## 3. 数据目录结构

```text
MarketData/<release>/
├── panels/
│   ├── market_data.parquet          # 后复权行情和流动性
│   ├── daily_basic.parquet          # 市值、股本和估值
│   └── security_status.parquet      # 行业、涨跌停、ST、是否停牌
├── display/
│   └── unadjusted_price.parquet     # WebApp 未复权 K 线
├── benchmark/
│   ├── index_price_<index>.parquet
│   └── index_weights_<index>.parquet
├── universe/
│   └── a_share.parquet              # 静态全 A 股票池
├── calendar/
│   └── trading_calendar.parquet
├── metadata/
│   └── security_master.parquet
├── data_manifest.yaml
└── quality_report.json
```

`MarketData/current` 指向当前活动 release。活动 release 只读，数据更新通过生成、校验并切换新 release 完成。

### 为什么按业务域组织多字段宽表？

1. **贴合读取模式**：价格和流动性、估值和股本等相关字段通常成组使用。
2. **减少资产碎片**：日期轴和证券轴不必在每个字段文件中重复维护，发布与校验以业务资产为单位。
3. **保持职责隔离**：研究行情、日频基本面、证券状态和展示价格分别更新，不形成一张难以治理的总表。
4. **不牺牲字段接口**：Provider 仍按字段返回“日期 × 证券”面板，服务器内存仍按字段保存只读二维数组。

股票日频多字段宽表使用 `(symbol, field)` 两级列。具体字段契约见 `../04-features/FEAT-024-ifind-storage-v2/03-technical-design.md`，其中 `security_status.parquet` 明确包含独立的 `is_suspended` 字段。

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
| CSV | 默认，人类可读 | `storage: csv` |
| Parquet | 大批量结果 | `storage: parquet` |
| SQLite | 需要 SQL 查询 | `storage: sqlite` |
| ClickHouse | 生产环境/大规模 | `storage: clickhouse` |

---

## 6. 数据流

```
外部数据源（iFinD / AKShare / CSV）
       ↓
  数据采集与候选 release 构建
       ↓
  按业务域多字段 Parquet（不可变发布）
       ↓
  Provider / DataEngine（统一字段接口）
       ↓
  MarketDataSnapshot（服务器只读内存快照）
       ↓
  FactorEngine（计算因子值 → numpy array）
       ↓
  BacktestEngine（回测）
       ↓
  output/（回测结果持久化）
```

---

## 7. 相关决策

- `../06-decisions/ADR-001-为什么使用向量化回测.md` — 向量化回测优先，Parquet 的列式读取对向量化计算友好
- `../06-decisions/ADR-003-为什么行情数据采用文件存储并选择Parquet.md` — 历史行情为何采用文件存储，以及为何以 Parquet 为标准格式
- `../06-decisions/ADR-016-Parquet持久化与只读内存快照.md` — 持久化版本与回测运行时内存快照的职责划分
- `../06-decisions/ADR-017-市场数据按业务域采用多字段宽表.md` — 股票日频数据的业务域多字段物理布局
- `system_architecture.md` — 架构总览中的数据层
