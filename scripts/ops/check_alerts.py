#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产巡检：健康/迁移/数据新鲜度/举报积压/磁盘 → 告警。

用法：
  python scripts/ops/check_alerts.py
  SVQ_API_BASE=http://127.0.0.1:8766 ALERT_WEBHOOK_URL=https://... python scripts/ops/check_alerts.py

退出码：0 无告警；2 有告警（便于 cron/systemd 告警联动）。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.core.ops_checks import evaluate_signals  # noqa: E402

BASE = (os.environ.get("SVQ_API_BASE") or "http://127.0.0.1:8766").rstrip("/")
TIMEOUT = float(os.environ.get("SVQ_ALERT_TIMEOUT_SEC") or "5")


def _get(path: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, TimeoutError):
        return None


def _metrics() -> str:
    try:
        headers = {}
        token = (os.environ.get("METRICS_TOKEN") or "").strip()
        if token:
            headers["X-Metrics-Token"] = token
        req = urllib.request.Request(f"{BASE}/api/metrics", headers=headers)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError):
        return ""


def _metric_value(text: str, name: str) -> int:
    for line in text.splitlines():
        if line.startswith(f"{name} "):
            try:
                return int(float(line.split(" ", 1)[1]))
            except ValueError:
                return 0
    return 0


def _notify(alerts) -> None:
    hook = (os.environ.get("ALERT_WEBHOOK_URL") or "").strip()
    if not hook:
        return
    text = "\n".join(f"[{a.level}] {a.code}: {a.message}" for a in alerts)
    body = json.dumps({"text": f"SVQuant 告警\n{text}"}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        hook, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=TIMEOUT).read()
    except (urllib.error.URLError, TimeoutError):
        print("[check_alerts] webhook 发送失败", file=sys.stderr)


def main() -> int:
    health = _get("/api/health")
    quality = _get("/api/invest/data-quality") or {}
    metrics = _metrics()
    disk_path = os.environ.get("SVQ_DISK_PATH") or str(ROOT)
    try:
        usage = shutil.disk_usage(disk_path)
        free_ratio = usage.free / usage.total
    except OSError:
        free_ratio = None

    alerts = evaluate_signals(
        health=health,
        data_age_days=quality.get("ageDays"),
        max_data_age_days=float(os.environ.get("SVQ_MAX_DATA_AGE_DAYS") or "2"),
        open_reports=_metric_value(metrics, "svquant_open_community_reports"),
        disk_free_ratio=free_ratio,
        min_disk_free_ratio=float(os.environ.get("SVQ_MIN_DISK_FREE") or "0.10"),
    )
    if not alerts:
        print("[check_alerts] OK")
        return 0
    for alert in alerts:
        print(f"[{alert.level}] {alert.code}: {alert.message}")
    _notify(alerts)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
