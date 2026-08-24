# FEAT-004：因子资产目录与回测结果缓存 — Technical Design

- 状态：已规划

## 1. 架构与模块边界

```text
API Route
  └─ FactorBacktestCache（ResearchEngine 编排层）
       ├─ FactorAssetPaths：解析 Factor/libraries 与 backtest_results
       ├─ CacheKeyBuilder：请求 + 算法版本 + 数据指纹 → SHA-256
       ├─ FileBacktestCache：读取、原子写入、锁与清理
       └─ run_factor_backtest_uncached：既有回测流程
```

- `Factor/` 只承载项目资产，不包含 Python 运行逻辑。
- 缓存编排属于 `ResearchEngine/app/repositories/results/cache/`，不得侵入 `app.quantcore` 回测引擎。
- `ResultStorage` 继续用于 SDK 的结果保存；不复用为 API 缓存，避免将缓存索引、失效和清理逻辑混入结果存储接口。

## 2. 目录迁移

| 旧位置 | 新位置 |
|--------|--------|
| `ResearchEngine/factor/*.py` | `Factor/libraries/*.py` |
| `ResearchEngine/factor/index.yaml` | `Factor/libraries/index.yaml` |
| `ResearchEngine/factor/*.md` | `Factor/libraries/*.md` |
| — | `Factor/backtest_results/`（运行时创建） |

新增路径解析工具，所有 `FactorLoader` 默认路径、`/api/factor-libraries`、`/api/factors/{library_name}`、示例和文档引用统一经该工具获取；不保留旧目录的双写或软链接，避免两个因子库来源分叉。

## 3. 缓存键

键值为以下规范化 JSON 的 SHA-256：

```json
{
  "cache_version": "factor-backtest-v1",
  "request": "FactorBacktestRequest 的完整 JSON（排序键）",
  "data_fingerprint": "MarketData 与目标 benchmark 相关 parquet 的文件元信息摘要"
}
```

`data_fingerprint` 覆盖 `MarketData/` 下的 Parquet 行情字段和 `benchmark/` 下本次基准文件；使用相对路径、`st_size` 与 `st_mtime_ns` 排序后计算 SHA-256。该策略优先保证正确性，任何数据改动都允许导致缓存失效。

## 4. 文件格式与并发

```text
Factor/backtest_results/
├── <key>.json.gz       # 完整 API 响应体
├── <key>.meta.json     # 创建/最后访问时间、大小、缓存版本
└── <key>.lock          # 短生命周期写锁
```

- 写入先落到同目录临时文件，再使用 `os.replace` 原子替换。
- 锁通过独占创建实现；等待方定期重试读取成品缓存。
- 等待超时后允许自行执行回测，但仍使用原子写入，最终结果不会损坏。
- 缓存命中仅更新元数据访问时间；更新失败不影响结果返回。

## 5. 接口影响与兼容

- `POST /api/backtest/factor` 请求体和响应体不新增必填字段。
- 新增响应头 `X-SVQuant-Cache: HIT | MISS | BYPASS`。
- 缓存配置通过服务端环境变量或配置文件提供，不向前端暴露缓存路径。
- `/api/factor-libraries` 改为扫描 `Factor/libraries/`；指定库因子通过 `/api/factors/{library_name}` 查询。

## 6. 回滚方案

设置 `SVQUANT_BACKTEST_CACHE_ENABLED=false` 可绕过缓存并保留新资产目录；若目录迁移出现问题，可将 `SVQUANT_FACTOR_DIR` 指回已备份的因子库目录。缓存目录可整体删除，数据可自动重建。

## 7. 测试策略

- 单元测试：键的稳定性、参数/数据变化失效、TTL/容量清理、损坏文件恢复。
- API 测试：首次 `MISS`、二次 `HIT`、响应体一致、响应头正确。
- 并发测试：同键并发写入不产生半成品。
- 回归测试：内置因子枚举、现有因子回测和全量 pytest。
