# -*- coding: utf-8 -*-
"""手机 Invest 读模型（PostgreSQL）。

- `schema.py`：`invest_*` 表、兼容视图与服务层快照重建。
- `rules.py`：确定性读模型（日报/个股/组合/检索），从原 invest-api 迁移。
- `db.py`：把 `?` 占位符适配到 psycopg 的薄连接包装。

SQLite 版本仅作为历史 MVP，运行路径已切到 PostgreSQL。
"""
from __future__ import annotations

__all__ = ["db", "rules", "schema"]
