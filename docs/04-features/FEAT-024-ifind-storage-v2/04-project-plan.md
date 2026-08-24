# Project Plan：iFinD 多字段宽表与只读运行时

## 1. 任务拆解

| 任务 | 交付物 | 复杂度 | 预计人天 |
|---|---|---:|---:|
| 固化三个研究宽表 schema | `market_data/daily_basic/security_status` 字段契约 | 2 | 1 |
| 生成候选多字段宽表 | AkShare 基线 + iFinD 渐进覆盖的新 release | 3 | 2 |
| 增加 `is_suspended` | 停牌字段映射/生成和读取测试 | 2 | 1 |
| 扩展持久化 Provider | 多文件两级列扫描、字段投影和兼容读取 | 3 | 2 |
| 更新 manifest 与发布切换 | 字段级来源、哈希、不可变版本和回滚 | 3 | 2 |
| 真实因子和策略回测 | 行情、估值、行业、停牌场景验证 | 3 | 1.5 |
| 首日股票池固定与展示行情切源 | 点时权重解析、未复权行情 API、回归测试 | 2 | 1 |
| 进程级内存快照 | 服务启动预加载、请求复用、版本信息 | 3 | 2 |
| 共享回测进程池 | Linux 预加载后 fork、并发上限、内存验证 | 4 | 3 |

预计 14-15 人天；若只完成磁盘宽表和单机回测验证，预计 7-8 人天。

## 2. 开发顺序

1. 生成 `market_data.parquet` 并验证七个字段投影读取。
2. 生成 `daily_basic.parquet`，保留 `pe` 与 `pe_ttm` 两个逻辑字段。
3. 生成 `security_status.parquet`，补齐 `is_suspended`。
4. 更新 Provider、manifest、发布和回滚流程。
5. 完成真实因子与策略回测。
6. 建立只读内存快照和 Linux 共享 worker 池。

当前已完成首日股票池固定解析与 `/api/market-data/` 未复权展示行情切源；指数动态注册、进程级内存快照和共享 worker 池仍是后续任务。

## 3. 里程碑

- M1：三个研究宽表和一个展示宽表 schema 固定。
- M2：候选 release 可被 Provider 按字段读取，`is_suspended` 可用于回测。
- M3：真实回测通过并支持 release 级回滚。
- M4：服务器正常请求只读取共享内存快照。
- M5：多用户压力测试期间不发生重复 Parquet 读取或基础数据副本膨胀。
