#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""向 background_jobs 投递一次数据同步任务（队列模式的入口，由 poll.sh 调用）。

用法：
  python scripts/ops/enqueue_data_sync.py [--view current] [--force]

前提：DATABASE_URL 指向目标库（生产由 sync_data_production.sh 从 deploy/.env 注入）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--view", default=os.environ.get("SYNC_VIEW", "current"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    from services.core.job_queue import ensure_job_schema
    from services.data.sync_jobs import enqueue_sync

    ensure_job_schema()
    job_id = enqueue_sync(args.view, force=args.force)
    print(json.dumps({"status": "queued", "job_id": job_id, "view": args.view}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
