# -*- coding: utf-8 -*-
"""B4：运维巡检信号判定。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.core.ops_checks import evaluate_signals  # noqa: E402

HEALTHY = {"ok": True, "db": "ok", "schema": {"ok": True, "pending": []}}


def test_healthy_has_no_alerts() -> None:
    assert evaluate_signals(health=HEALTHY, data_age_days=0, disk_free_ratio=0.5) == []


def test_health_and_db_down_are_critical() -> None:
    codes = {a.code for a in evaluate_signals(health=None)}
    assert "health_down" in codes
    codes = {a.code for a in evaluate_signals(health={"ok": True, "db": "error"})}
    assert "db_down" in codes


def test_pending_migrations_and_stale_data() -> None:
    alerts = evaluate_signals(
        health={"ok": True, "db": "ok", "schema": {"pending": ["0002_x"]}},
        data_age_days=3.5,
        max_data_age_days=2,
    )
    codes = {a.code for a in alerts}
    assert "migrations_pending" in codes
    assert "data_stale" in codes


def test_data_sync_failure_is_critical() -> None:
    health = {
        **HEALTHY,
        "data_sync": {
            "status": "failed",
            "view_id": "research-rv-test",
            "last_error": "contract mismatch",
        },
    }
    alerts = evaluate_signals(health=health)
    assert any(a.code == "data_sync_failed" and a.level == "critical" for a in alerts)


def test_disk_and_backlog() -> None:
    alerts = evaluate_signals(
        health=HEALTHY,
        open_reports=300,
        max_open_reports=200,
        queue_backlog=150,
        max_queue_backlog=100,
        disk_free_ratio=0.03,
        min_disk_free_ratio=0.10,
    )
    codes = {a.code: a.level for a in alerts}
    assert codes["reports_backlog"] == "warning"
    assert codes["queue_backlog"] == "warning"
    assert codes["disk_low"] == "critical"

def test_db_pool_thresholds() -> None:
    warn = evaluate_signals(health=HEALTHY, db_pool_used=83, db_pool_limit=100)
    assert any(a.code == "db_pool_high" and a.level == "warning" for a in warn)
    crit = evaluate_signals(health=HEALTHY, db_pool_used=96, db_pool_limit=100)
    assert any(a.code == "db_pool_high" and a.level == "critical" for a in crit)
    assert evaluate_signals(health=HEALTHY, db_pool_used=50, db_pool_limit=100) == []

def test_db_connections_thresholds() -> None:
    warn = evaluate_signals(health=HEALTHY, db_connections_used=85, db_connections_limit=100)
    assert any(a.code == "db_connections_high" and a.level == "warning" for a in warn)
    crit = evaluate_signals(health=HEALTHY, db_connections_used=92, db_connections_limit=100)
    assert any(a.code == "db_connections_high" and a.level == "critical" for a in crit)
    assert evaluate_signals(health=HEALTHY, db_connections_used=50, db_connections_limit=100) == []
