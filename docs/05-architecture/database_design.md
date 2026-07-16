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

**决策**：行情数据和因子数据使用 **Parquet** 存储，按"一个字段一个文件"组织（FieldParquetProvider）。回测结果可选 CSV / Parquet / SQLite / ClickHouse。

### 2.2 给老板的解释

**Parquet 比 CSV 好在哪？**

CSV 存股票数据，要查"所有股票某一天的收盘价"需要读整个文件。Parquet 只读需要的列，速度快 10-100 倍，而且文件体积只有 CSV 的 1/3。

**为什么不用数据库？**
因为量化的分析场景（算 IC、回测）需要把所有数据加载到内存做矩阵运算，数据库的查询接口反而成为瓶颈。Parquet 作为文件格式，加载快、生态好、无需部署。

---

## 3. 数据目录结构

```
MarketData/                          # 行情数据根目录
├── stocks/                          # A 股
│   ├── daily/                       # 日线
│   │   ├── open.parquet             # 开盘价（字段独立存储）
│   │   ├── high.parquet
│   │   ├── low.parquet
│   │   ├── close.parquet
│   │   ├── volume.parquet
│   │   ├── amount.parquet
│   │   └── adj_factor.parquet       # 复权因子
│   ├── minute/                      # 分钟线
│   │   ├── close_1min.parquet
│   │   └── ...
│   └── fundamentals/                # 基本面
│       ├── pe.parquet
│       ├── pb.parquet
│       ├── market_cap.parquet
│       └── ...
├── industry/                        # 行业分类
│   ├── sw_industry.parquet          # 申万行业
│   └── zx_industry.parquet          # 中信行业
└── index/                           # 指数
    └── ...
```

### 为什么按字段存储？

1. **查询按需加载**：算 IC 只需要因子值和收益率，不需要成交量数据
2. **并行计算友好**：不同字段可以并行读取
3. **字段类型独立**：价格用 float64，成交量用 int64，不互相影响

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
外部数据源（Wind / AKShare / CSV）
       ↓
  FieldParquetProvider（转为 Parquet 存储）
       ↓
  DataEngine（统一读取接口）
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
- `system_architecture.md` — 架构总览中的数据层
