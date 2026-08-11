# iFinD 采集产物目录治理

- 状态：已完成
- 所属 Feature：FEAT-010 投研因子数据底座
- 规模：S（内部路径治理，约 1 人天）
- 宏观影响：L0（不新增产品能力，不改变模块边界）

## 背景与价值

`MarketData/sources/ifind/` 曾同时放置业务最终文件、不同价格口径的原始响应、探针文件、迁移中间产物和运行日志。调用方难以判断哪些文件仍由当前脚本维护，历史缓存也可能被新任务误读。按业务域收口后，维护者可以从目录直接识别资产归属，降低错误复权、误重放和手工清理风险。

## 范围

必须做：

- 保持 `--output-root` 仍表示 `sources/ifind/` 根目录，兼容现有命令调用方式。
- `calendar`、`universe`、`market_data`、`unadjusted_price`、`date_sequence` 与 `index` 各自管理本域 raw、CSV 和 Parquet；`index` 下再按权重和价格分域。
- 回测价格与流动性分别落在 `market_data/raw/price/`、`market_data/raw/liquidity/`；未复权 OHLC 落在 `unadjusted_price/raw/`。
- 根目录不再生成 CSV、Parquet 或原始响应。
- 迁移现有有效缓存到新路径；无法确认用途的旧文件移入 `archive/2026-08-11-pre-domain-layout/`，不删除。

明确不做：

- 不改变 iFinD 请求参数、字段、复权口径或 CSV/Parquet schema。
- 不将采集产物直接发布到 `current/` 或 `releases/`。
- 不自动删除归档数据，不引入通用配置系统或数据库。

## 目标目录

```text
sources/ifind/
├── calendar/{raw,calendar_all_a.csv,calendar_all_a.parquet}
├── universe/{raw,a_share.csv,a_share.parquet}
├── market_data/{raw/price,raw/liquidity,market_data_hfq.csv,market_data_hfq.parquet}
├── unadjusted_price/{raw,unadjusted_price.csv,unadjusted_price.parquet}
├── date_sequence/{raw,date_sequence.csv,date_sequence.parquet}
├── index/
│   ├── index_weights/{raw,index_weights_<index>.csv,index_weights_<index>.parquet}
│   └── index_price/{raw,index_price_<index>.csv,index_price_<index>.parquet}
├── logs/
└── archive/2026-08-11-pre-domain-layout/
```

## 技术与迁移方案

下载分组显式声明完整的 `raw_root`，共享下载器不再隐式追加供应商旧目录。各 CSV/Parquet 脚本将最终文件写入本业务目录；每日总更新复用同一契约。迁移只在同一 `sources/ifind/` 下移动文件：当前后复权 raw、流动性 raw 和最终文件迁入 `market_data/`；旧扁平行情、旧交易所日历、探针和迁移中间文件进入日期化归档。回滚时可将对应文件移回原路径并恢复上一版代码。

## 验收标准

1. 三阶段测试证明 market data、unadjusted price 和 date sequence 的 raw 与最终文件都位于各自业务目录。
2. 每日更新传给 Parquet 转换器的路径为 `market_data/market_data_hfq.csv/.parquet`。
3. 测试输出根目录不存在 CSV 或 Parquet。
4. 现有有效 raw 分区和最终后复权文件迁移后数量、大小不变，且脚本可从新目录重放。
5. 历史遗留文件均可在日期化归档中恢复，本次不删除任何数据。
6. 原 `index_weights/` 的文件无损迁入 `index/index_weights/`；指数价格仅写入 `index/index_price/`，旧路径不再生成。

## 计划与风险

任务：路径契约与测试（复杂度 2，低风险）→ 脚本修改（复杂度 2，中风险）→ 本地数据迁移与数量校验（复杂度 2，中风险）→ 回归测试（复杂度 1，低风险）。主要风险是移动中断或新旧目录同时存在导致读取分叉；通过同盘原子移动、迁移前后统计和精确目录读取缓解。里程碑为：M1 路径测试通过，M2 本地数据迁移完成，M3 iFinD 测试集通过。

## 验证记录（2026-08-11）

- `MarketData/DataIngestion` 全部 47 项测试通过。
- 全仓回归测试 270 项通过；仅保留既有 Starlette/httpx 弃用警告。
- `market_data/raw/price` 迁移前后均为 14,335 个文件、957,056,323 字节。
- `market_data/raw/liquidity` 迁移前后均为 14,335 个文件、628,571,292 字节。
- `market_data_hfq.csv` 与 Parquet 已迁入业务目录，文件大小未变化。
- `sources/ifind/` 根目录已无文件；14 个明确旧路径均不存在。
- 4,472 个遗留文件、共 3,657,649,623 字节已移入 `archive/2026-08-11-pre-domain-layout/`，本次未删除数据。
- 原 `sources/ifind/index_weights` 的 2,333 个文件、30,566,031 字节已无损迁入 `sources/ifind/index/index_weights`；旧路径已不存在。
- `index/index_price` 已建立固定 OHLC 管道，请求不含复权参数或成交字段；下载协议、CSV/Parquet 与每日更新测试通过。
- 指数权重和指数价格最终产物已分别增加 `index_weights_` 与 `index_price_` 前缀，脱离目录后仍可区分。
