"""每日因子批量回测 HTTP 客户端。

CLI 不创建 Manager、不读取行情，也不执行因子；所有工作交给运行中的
``app.main`` FastAPI 进程。
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="触发 SVQuant 每日因子批量回测")
    parser.add_argument("run", choices=["run"])
    parser.add_argument("--as-of", required=True, dest="as_of_date")
    parser.add_argument("--force-retry", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SVQUANT_API_URL", "http://127.0.0.1:8000"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = json.dumps(
        {
            "as_of_date": args.as_of_date,
            "force_retry": args.force_retry,
            "dry_run": args.dry_run,
        }
    ).encode("utf-8")
    url = args.base_url.rstrip("/") + "/api/internal/factor-backtests/batches"
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            print(body)
            return 0 if response.status < 400 else 1
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"))
        return 1
    except urllib.error.URLError as exc:
        print(json.dumps({"status": "failed", "error": str(exc.reason)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
