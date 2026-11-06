# -*- coding: utf-8 -*-
"""后台调度器启动入口；可留在 API 进程，也可由独立 worker 承担。

`SVQUANT_SCHEDULER_MODE=inline`（默认）由 API 启动；
`worker` 时 API 跳过，由 `worker.py` 启动，避免长任务和 Web 请求抢资源。
"""
from __future__ import annotations


def start_all() -> None:
    try:
        from services.news.news_ingest import start_news_ingest_scheduler

        start_news_ingest_scheduler()
    except Exception as exc:  # noqa: BLE001
        print(f"  news ingest scheduler 跳过: {exc}")

    try:
        from services.factor.dashboard_scheduler import start_dashboard_daily_scheduler

        start_dashboard_daily_scheduler()
    except Exception as exc:  # noqa: BLE001
        print(f"  panel daily scheduler 跳过: {exc}")

    try:
        from services.paper.scheduler import start_paper_settlement_scheduler

        start_paper_settlement_scheduler()
    except Exception as exc:  # noqa: BLE001
        print(f"  paper trading scheduler 跳过: {exc}")

    try:
        from services.factor.catalog_scheduler import start_re_catalog_sync_scheduler

        start_re_catalog_sync_scheduler()
    except Exception as exc:  # noqa: BLE001
        print(f"  re-catalog 定时同步跳过: {exc}")


__all__ = ["start_all"]
