"""因子批量回测 HTTP 客户端。

CLI 不创建 Manager、不读取行情，也不执行因子；所有工作交给运行中的
``app.main`` FastAPI 进程。
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


_TERMINAL_STATUSES = {"succeeded", "failed"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="触发 SVQuant 因子批量回测")
    parser.add_argument("run", choices=["run"])
    parser.add_argument("--as-of", required=True, dest="as_of_date")
    parser.add_argument("--force-retry", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--filter-suspended", action="store_true")
    parser.add_argument("--filter-limit-up", action="store_true")
    parser.add_argument("--winsorize", type=int, choices=range(4), default=0)
    parser.add_argument("--standardize", type=int, choices=range(4), default=0)
    parser.add_argument(
        "--wait",
        action="store_true",
        help="提交后轮询任务直到批量回测结束",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="--wait 的轮询间隔（秒）",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SVQUANT_API_URL", "http://127.0.0.1:8000"),
    )
    return parser


def _request_json(
    url: str,
    *,
    method: str,
    payload: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
        method=method,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("API 返回的 JSON 顶层必须是对象")
        return response.status, body


def _poll_url(base_url: str, poll_url: str) -> str:
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", poll_url.lstrip("/"))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _, submission = _request_json(
            args.base_url.rstrip("/") + "/api/internal/factor-backtest-batches",
            method="POST",
            payload={
                "as_of_date": args.as_of_date,
                "force_retry": args.force_retry,
                "dry_run": args.dry_run,
                "filter_suspended": args.filter_suspended,
                "filter_limit_up": args.filter_limit_up,
                "winsorize": args.winsorize,
                "standardize": args.standardize,
            },
        )
        if not args.wait:
            print(json.dumps(submission, ensure_ascii=False))
            return 0

        poll_url = submission.get("poll_url")
        if not isinstance(poll_url, str) or not poll_url:
            raise ValueError("批量回测提交响应缺少 poll_url")
        if args.poll_interval < 0:
            raise ValueError("poll_interval 不能小于 0")
        while True:
            _, task = _request_json(
                _poll_url(args.base_url, poll_url),
                method="GET",
            )
            status = task.get("status")
            if status in _TERMINAL_STATUSES:
                print(json.dumps(task, ensure_ascii=False))
                return 0 if status == "succeeded" else 1
            time.sleep(args.poll_interval)
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"))
        return 1
    except urllib.error.URLError as exc:
        print(json.dumps({"status": "failed", "error": str(exc.reason)}, ensure_ascii=False))
        return 1
    except (TypeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
