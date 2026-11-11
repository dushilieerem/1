# -*- coding: utf-8 -*-
"""P2-09：关键 API 契约存在性（防止路由被误删/改名）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

EXPECTED = {
    "/api/market-data/minute/{symbol}": {"get"},
    "/api/market-data/fundamentals/{symbol}": {"get"},
    "/api/market-data/availability": {"get"},
    "/api/market-data/indices/catalog": {"get"},
    "/api/market-data/fields/samples": {"get"},
    "/api/market-data/indicators/{symbol}": {"get"},
    "/api/market-data/financials/{symbol}": {"get"},
    "/api/market-data/financials/fields": {"get"},
    "/api/backtest/minute": {"post"},
    "/api/factor/attribution": {"post"},
    "/api/factor/combo": {"post"},
    "/api/agent/research-runs": {"get", "post"},
    "/api/agent/knowledge/search": {"post"},
    "/api/ai/conversations": {"get", "post"},
    "/api/community/posts/{post_id}/ai-review": {"post"},
    "/api/admin/news/sources": {"get"},
    "/api/admin/news/ingest-health": {"get"},
    "/api/admin/re-catalog/status": {"get"},
    "/api/invest/ai/compare": {"post"},
    "/api/invest/ai/paper": {"post"},
    "/api/invest/ai/quant": {"post"},
    "/api/invest/ai/voice": {"post"},
    "/api/invest/ai/deep": {"post"},
    "/api/invest/ai/backtest": {"post"},
    "/api/invest/event-logs": {"get"},
    "/api/invest/event-logs/read": {"post"},
    "/api/invest/portfolio/penetration": {"get"},
    "/api/invest/risk-scan": {"post"},
    "/api/invest/events/scan": {"post"},
    "/api/invest/quant/select": {"get"},
    "/api/invest/quant/signals": {"get"},
    "/api/inst/quant/factor-workflow/autonomy/agent": {"get"},
    "/api/inst/quant/factor-workflow/autonomy/agent/enable": {"post"},
    "/api/inst/quant/factor-workflow/autonomy/agent/disable": {"post"},
}


def test_expected_routes_exist() -> None:
    paths = app.openapi().get("paths") or {}
    missing: list[str] = []
    for path, methods in EXPECTED.items():
        if path not in paths:
            missing.append(path)
            continue
        for method in methods:
            if method not in paths[path]:
                missing.append(f"{method.upper()} {path}")
    assert not missing, f"缺少契约路由: {missing}"
