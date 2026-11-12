# -*- coding: utf-8 -*-
"""跨进程/跨实例任务锁（P1-O06）：PostgreSQL advisory lock。

单机内已有 flock 的地方保留 flock；需要多实例互斥的后台任务（资讯抓取、
目录同步等）用本模块。锁随连接关闭自动释放，进程被杀不会留死锁。
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


@contextmanager
def advisory_lock(name: str, *, timeout_sec: float = 0) -> Iterator[bool]:
    """尝试获取命名锁；timeout_sec=0 表示不等待。yield 是否拿到锁。"""
    from services.core.db import get_conn

    key = str(name or "").strip()
    if not key:
        yield True
        return
    try:
        with get_conn(autocommit=True) as conn:
            row = conn.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s)) AS ok", (key,)
            ).fetchone()
            acquired = bool(row and row.get("ok"))
            if not acquired and timeout_sec > 0:
                # 简单轮询等待（避免引入额外依赖）
                import time

                deadline = time.monotonic() + timeout_sec
                while not acquired and time.monotonic() < deadline:
                    time.sleep(0.5)
                    row = conn.execute(
                        "SELECT pg_try_advisory_lock(hashtext(%s)) AS ok", (key,)
                    ).fetchone()
                    acquired = bool(row and row.get("ok"))
            try:
                yield acquired
            finally:
                if acquired:
                    conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (key,))
    except Exception:
        # 数据库不可用时不阻塞任务（限流/锁降级为放行）
        yield True
