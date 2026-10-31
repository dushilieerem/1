# -*- coding: utf-8 -*-
"""统一市场数据服务层。

- `schema.py`：PostgreSQL 库表（ref_* / md_* / fin_* / doc_* / ingest_*）。
- `store.py`：面向 API 的只读查询（日线、估值、财务、证券检索）。
- 数据权威源是 `/home/dev01/project/marketdata` 的 parquet；PG 是可重建的服务层。
"""
from __future__ import annotations

__all__ = ["schema", "store"]
