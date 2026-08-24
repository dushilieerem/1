# Verification：因子批量回测与指标仓库

## 自动化测试矩阵

| 场景 | 覆盖 |
|---|---|
| 滚动十年日期和固定配置 | `test_profile_uses_rolling_calendar_years_and_fixed_defaults` |
| IC、RankIC、ICIR 汇总 | `test_predictive_summary_returns_scalar_ic_rank_ic_and_annualized_icir` |
| 六行分组指标和预测性指标入库 | `test_store_round_trip_persists_six_quantile_rows_and_predictive_metrics` |
| 成功/失败隔离、幂等和 force-retry | `test_batch_is_idempotent_and_force_retry_supersedes` |
| 批量窗口不超过 2、完成一个才补一个、交互任务保持 FIFO | `test_factor_backtest_batch_owns_two_slot_fifo_window` |
| 索引/预检失败批次 | `test_index_or_preflight_failure_is_recorded_as_failed_batch` |
| 抽象 Experiment 和 Manager 拒绝 callable | `test_experiment_contract.py`、`test_experiment_manager.py` |
| HTTP 过滤、分页、历史 | `test_read_only_http_queries_support_filters_and_history` |
| 任务提交立即返回、轮询、去重和 force-retry | 批量任务注册表/API 测试 |
| 启动不自动执行批量、关闭顺序为注册表先于 Manager | `tests/api/test_v2_contract.py` |
| 既有回测/API 行为 | `ResearchEngine/tests/test_research.py`、`test_api.py` |

## 发布前检查

1. 启动 `uvicorn app.main:app --workers 1`，在包含 CSI_ALL、CSI300 和必要字段的
   `MarketData/current` 上通过 HTTP/CLI 按指定 `as_of_date` 执行 `--dry-run`。
2. 选取 50 个代表因子记录总耗时、单因子耗时、内存和失败分类。
3. 验证数据库只新增四张标量/状态表，不生成曲线或每日 IC 文件。
4. 中断进程后重新运行，确认 `running` 因子可续跑且已完成因子不重复计算。
5. 用 Windows 任务计划或其它调度器调用 HTTP CLI 显式传入 `--as-of`，检查批量任务提交和轮询。
6. 生产试跑后复核成功因子均有六行分组指标和一行预测性指标。

## 当前已验证

专项测试 9 项通过，既有 ResearchEngine/API 回归 92 项通过。全项目回归 406 项通过。真实 1055 因子全量耗时基准
依赖本机 `MarketData/current`，在数据可用后作为 M3 验证项执行。

本机 `MarketData/current` 的 `2026-08-14` dry-run 已确认 1055 个因子、5916 个全 A 标的和
CSI300 基准均可预检；`2026-08-19` 因基准尚未发布到该日期而按预期拒绝。
