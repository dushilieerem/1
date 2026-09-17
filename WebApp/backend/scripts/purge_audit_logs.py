# -*- coding: utf-8 -*-
"""手动清理过期审计日志。

用法（在 WebApp 目录）:
  python backend/scripts/purge_audit_logs.py
  python backend/scripts/purge_audit_logs.py --days 14
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    try:
        from services.core.env_config import load_env

        load_env()
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Purge old app_audit_logs rows")
    ap.add_argument(
        "--days",
        type=int,
        default=None,
        help="保留最近 N 天（默认 AUDIT_LOG_RETENTION_DAYS 或 30）",
    )
    args = ap.parse_args()
    days = args.days
    if days is None:
        days = int(os.environ.get("AUDIT_LOG_RETENTION_DAYS", "30") or "30")

    from services.core.audit_log_store import purge_audit_logs

    n = purge_audit_logs(days=days)
    print(f"deleted={n} retention_days={days}")


if __name__ == "__main__":
    main()
