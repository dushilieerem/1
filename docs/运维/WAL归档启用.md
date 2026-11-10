# WAL 归档启用与验证（PITR 第一步）

> 目标：把恢复粒度从「上一次全量备份」提升到「任意时间点」，RPO ≤ 5 分钟。
> 本页只覆盖启用与验证；完整方案（基础备份节奏、恢复演练、大表分区）见
> [数据库恢复与分区方案](数据库恢复与分区方案.md)。

## 1. 改了什么

| 文件 | 改动 |
|---|---|
| `deploy/compose.yml` | db 服务增加 `/backup` 挂载与 `archive_mode=on`、`archive_timeout=300`、`archive_command=cp %p /backup/%f` |
| `scripts/ops/pg_wal_setup.sh` | 创建宿主机归档目录并放开写权限（容器内 postgres 是 uid 70） |
| `scripts/ops/pg_basebackup.sh` | 每周基础备份 + 保留策略（基础备份 4 份、WAL 14 天） |

归档目录默认 `/home/dev01/svquant-wal-archive`，可用 `WAL_ARCHIVE_HOST_DIR` 覆盖。
刻意放在 `/home`（数据盘是 `/data`），机器级故障时归档不会跟着数据盘一起丢。

## 2. 启用步骤

```bash
# 1) 建目录（普通用户即可）
bash scripts/ops/pg_wal_setup.sh

# 2) 走正常发布流程（合并后打 tag）
#    发布时 db 容器会因配置变化被重建，期间约 10~30 秒不可用
# 3) 验证
docker exec svquant-db-1 psql -U svquant -c "SHOW archive_mode; SHOW archive_command;"
docker exec svquant-db-1 psql -U svquant -c "SELECT archived_count, failed_count, last_archived_wal, last_archived_time FROM pg_stat_archiver;"
ls -lt deploy/wal-archive | head
```

预期：`archive_mode=on`；`archived_count` 随时间增长；`failed_count` 保持 0；归档目录出现 `000000010000...` 文件。

## 3. 基础备份

```bash
bash scripts/ops/pg_basebackup.sh      # 手动
```

已经挂在轮询上：**每周日 04:00–04:59 的第一次轮询触发，一周只跑一次**（标记
`/var/lib/svquant/basebackup.week`，日志 `basebackup.log`）。手动补跑：

```bash
WEEKLY_BASEBACKUP_FORCE=1 bash scripts/ops/pg_basebackup.sh
```

脚本会校验 `base.tar.gz`、清理第 5 份之前的基础备份和 14 天前的 WAL。

## 4. 监控

`/api/health` 的 `wal_archive` 字段暴露 `archived` / `failed` / `age_sec`；
`scripts/ops/check_alerts.py` 会对 `failed>0` 告警（critical）、对
`age_sec > 1800`（30 分钟，可用 `SVQ_WAL_ARCHIVE_MAX_AGE_SEC` 调整）告警（warning）。

`pg_stat_archiver.failed_count` 持续增长、或归档长时间没有推进，
说明归档失败——此时 WAL 会在 `pg_wal` 里堆积，`max_wal_size`（1GB）之后会触发强制检查点，
磁盘可能被吃满。

排查顺序：

```bash
docker exec svquant-db-1 psql -U svquant -c "SELECT * FROM pg_stat_archiver;"
docker logs --tail 50 svquant-db-1 | grep -i archive
df -h /home          # 归档盘
ls -l deploy/wal-archive | tail
```

应急：空间不足时先确认最老的基础备份，再手工清理更早的 WAL；实在不行回退
`archive_mode=off` 并重启 db（会失去 PITR 能力）。

## 5. 恢复（演练用）

```bash
# 起独立实例，不复用生产卷
docker run -d --name pg-restore -e POSTGRES_PASSWORD=... -p 55440:5432 postgres:16-alpine
# 解基础备份
docker exec -i pg-restore sh -c 'cd /var/lib/postgresql/data && tar xzf -' < deploy/wal-archive/base/<时间戳>/base.tar.gz
# 写恢复配置（restore_command + recovery_target_time），启动，确认后 promote
```

完整命令与注意事项见方案文档第 2.3 节。

## 6. 回滚

- 配置回滚：删掉 `deploy/compose.yml` 中 db 的 `command` 与 `/backup` 挂载，重新发布；
- 运行期回滚：`ALTER SYSTEM SET archive_mode=off;` + 重启 db（`archive_mode` 需要重启生效）。
