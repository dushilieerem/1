# 数据库设计

本目录描述 SVQuant 自有 PostgreSQL 数据、产品缓存和外部研究数据的所有权边界。

## 文档

- [数据库设计](数据库设计.md)：存储所有权、数据生命周期、PostgreSQL 与外部资源边界。
- `数据库持续更新.md`：由脚本从当前 `DATABASE_URL` 连接的数据库生成，记录表结构、行数和脱敏样例；文件仅在运行生成脚本后出现。

## 刷新数据库清单

```bash
conda activate svquant
cd backend
python scripts/refresh_database_docs.py
```

脚本访问已配置的 PostgreSQL。提交生成结果前应检查行数、字段和样例，确认没有业务敏感信息；不要把密码、Token、API Key 或用户数据写入文档。
