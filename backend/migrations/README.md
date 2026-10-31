# 数据库迁移（P0-10）

- 文件名：`NNNN_描述.sql`，按数字顺序执行；每个文件一个事务。
- 已执行版本记录在 `schema_migrations(version, checksum, applied_at)`。
- 启动时 `app/bootstrap.py` 调用 `apply_migrations()`：执行 pending；失败抛错（fail-fast）。
- 手工查看 / 执行：

```bash
cd backend
python -m services.core.migrations status
python -m services.core.migrations apply
```

- `0001_baseline.sql` 只登记现有 schema；新增变更请加 `0002_*.sql`。
- 回滚：当前以“向前修复”为主；涉及数据删除的迁移必须先写备份/回滚说明。
