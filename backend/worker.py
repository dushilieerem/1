# -*- coding: utf-8 -*-
"""独立后台 worker：消费量化因子长任务队列。

用法：
  QUANT_FACTOR_JOB_MODE=queue python -u worker.py
需要与 API 共用 DATABASE_URL / YG_RE_BASE；不启动 HTTP、不跑迁移。
"""
from __future__ import annotations

import signal
import sys
import threading
import time

ROOT = __file__.rsplit("/", 1)[0]
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    from services.core.job_queue import ensure_job_schema
    from services.quant_factor.jobs import start_worker

    for attempt in range(30):
        try:
            ensure_job_schema()
            break
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] database not ready ({attempt + 1}/30): {exc}", file=sys.stderr)
            time.sleep(2)
    else:
        print("[worker] database unavailable, exit", file=sys.stderr)
        return 1

    start_worker(poll_sec=2.0)
    stop = threading.Event()

    def _stop(_signum, _frame) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    print("[worker] quant.factor workers started", file=sys.stderr)
    while not stop.wait(30):
        pass
    print("[worker] stopped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
