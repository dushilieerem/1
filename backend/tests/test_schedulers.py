# -*- coding: utf-8 -*-
"""调度器启动入口：独立 worker 模式可复用同一组调度器。"""
from __future__ import annotations

from unittest.mock import patch

from services.core import schedulers


def test_start_all_starts_each_scheduler():
    with patch("services.news.news_ingest.start_news_ingest_scheduler") as news, \
         patch("services.factor.dashboard_scheduler.start_dashboard_daily_scheduler") as panel, \
         patch("services.paper.scheduler.start_paper_settlement_scheduler") as paper, \
         patch("services.factor.catalog_scheduler.start_re_catalog_sync_scheduler") as catalog:
        schedulers.start_all()
    news.assert_called_once()
    panel.assert_called_once()
    paper.assert_called_once()
    catalog.assert_called_once()


def test_start_all_isolates_failures():
    with patch("services.news.news_ingest.start_news_ingest_scheduler", side_effect=RuntimeError("x")), \
         patch("services.factor.dashboard_scheduler.start_dashboard_daily_scheduler") as panel, \
         patch("services.paper.scheduler.start_paper_settlement_scheduler") as paper, \
         patch("services.factor.catalog_scheduler.start_re_catalog_sync_scheduler") as catalog:
        schedulers.start_all()
    panel.assert_called_once()
    paper.assert_called_once()
    catalog.assert_called_once()
