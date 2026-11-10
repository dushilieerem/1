-- 0001 baseline
-- 现有 schema 由 app/bootstrap.py 的 ensure_*_schema() 创建；本迁移只登记基线。
-- 之后的增量变更一律新增 0002_*.sql、0003_*.sql，不再把 DDL 散落在启动代码里。
SELECT 1;
