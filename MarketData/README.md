# MarketData 数据目录

`MarketData/` 是 SVQuant 的运行时数据根目录。数据文件默认不纳入 Git；只有本说明和 `DataIngestion/` 下的采集、校验、发布代码纳入版本管理。

## 目录职责

```text
MarketData/
├── current/                         # 当前活动版本；API / 回测只读
│   ├── panels/                      # 业务域宽表 Parquet（日期 × 证券）
│   ├── benchmark/                   # 指数价格与成分权重
│   ├── calendar/                    # 全 A 交易日历
│   ├── universe/                    # 全 A 证券池
│   ├── metadata/                    # 证券主数据及运行报告
│   ├── display/                     # WebApp 展示用行情
│   ├── data_manifest.yaml           # 活动版本、来源、字段和哈希
│   └── quality_report.json          # 活动版本质量结果
├── sources/                         # 来源原始层；不得被读取层直接使用
│   ├── ifind/                       # 当前 iFinD 采集域、CSV/Parquet、raw 和日志
│   └── akshare/                     # 保留的免费源原始库（基本面等字段补齐）
├── releases/                        # 候选及历史发布版本；不可作为默认读取入口
├── backups/                         # current 切换前的可恢复备份
└── DataIngestion/                   # 纳入 Git 的采集、校验和发布代码
    ├── data_ingestion/              # iFinD 管道与共享发布组件
    ├── tests/                       # DataIngestion 回归测试
    └── ifind_pipeline.html          # iFinD 管道可视化说明
```

## 当前活动版本

以 `current/data_manifest.yaml` 为唯一事实来源。当前清单标记为 `release_status: active`，`data_version` 为 `ifind-sync-20260812-114015`。当前版本采用混合来源：行情、日历、证券池和证券状态主要来自 iFinD，部分估值和股本字段来自保留的免费源；每个字段的实际来源以清单为准。

`FieldParquetProvider("MarketData")` 只读取 `current/`，不会扫描 `sources/`、`releases/` 或 `backups/`。

## 发布与回滚规则

1. 原始响应和人工可检查的 CSV 先写入 `sources/<provider>/<domain>/`。
2. 通过字段、日期、证券轴、缺失率、哈希和授权检查后，生成 `releases/<data_version>/` 候选版本。
3. 候选版本完成质量检查后，才可以原子切换到 `current/`；切换前的文件进入 `backups/`。
4. `releases/` 和 `backups/` 只用于审计、复现和回滚，不应直接作为 API 数据目录。
5. 失败任务的临时日志、空版本目录和锁文件不保留在数据根目录；日志应归入对应来源的 `logs/`。

## 本次整理记录（2026-08-14）

- 清理已废弃的 Wind 原始样例目录。
- 删除空的旧版本目录、旧任务输出日志和遗留锁文件。
- 保留 `current/`、iFinD/免费源原始库、有效历史 release 及 rollback backups，不删除大体积业务数据。
- 历史版采集入口已从 `DataIngestion/` 移除；新数据源接入按 Feature 数据契约建立独立模块。

数据契约与发布要求见 `docs/04-features/FEAT-010-research-data-foundation/`；免费基本面与证券状态补齐见 `docs/04-features/FEAT-025-free-basic-status-mvp/`。
