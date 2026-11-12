# marketdata 数据发布与回滚 SOP（P1-O07）

> 适用：ResearchEngine / SVQuant 共用的 `marketdata/` release。
> 工具：`scripts/data_release.py`（check / snapshot / rollback）。

## 1. 发布前核对

```bash
# 快速核对：清单文件、资产存在性、非空
python scripts/data_release.py check --data-dir /data/marketdata

# 完整核对：逐文件 sha256（大 release 较慢）
python scripts/data_release.py check --data-dir /data/marketdata --checksum
```

必须全部通过（`ok: true`）才允许切换。记录输出中的 `data_version` 与 `generated_at`。

## 2. 备份当前版本

```bash
python scripts/data_release.py snapshot \
  --data-dir /data/marketdata \
  --out /data/releases/$(date +%Y%m%d-%H%M)-before
```

`snapshot` 只备份清单与质量报告；完整的资产备份由发布目录本身承担
（新 release 必须先落到独立目录，核对通过后再切换）。

## 3. 切换步骤（人工审批）

1. 确认 `check --checksum` 全绿，记录版本号。
2. 停写：暂停资讯抓取/面板日更（`SVQUANT_PANEL_DAILY_ENABLED=0` 或直接停后端）。
3. 备份当前目录（第 2 步）。
4. 用新 release 覆盖 `/data/marketdata`（推荐软切换：`current` 符号链接指向新目录）。
5. 启动后端，检查 `/api/health`、`/api/market-data/availability` 的 `data_version`。
6. 抽查：`/api/market-data/daily-local/000001.SZ?start=...`、`/api/market-data/indices/catalog`。
7. 恢复调度。

## 4. 回滚

```bash
# 先 dry-run，确认版本与文件
python scripts/data_release.py rollback \
  --data-dir /data/marketdata \
  --from /data/releases/20261030-before

# 确认后执行；会在数据目录内生成 .rollback_backup-<时间戳>
python scripts/data_release.py rollback \
  --data-dir /data/marketdata \
  --from /data/releases/20261030-before \
  --apply
```

回滚后重复第 3 步的 5–6 项检查。

## 5. 版本对比与追责

- 发布目录保留 `RELEASE_INFO.json`（快照时间、来源、清单路径）。
- 每次切换在变更单中记录：旧/新 `data_version`、核对输出摘要、操作人、时间。
- 若 `check` 报告 sha256 不一致，禁止切换；先重新同步 release。
