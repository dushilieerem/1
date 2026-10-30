#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WebHook 本地自测：按 Gitee 的签名算法给 127.0.0.1 发一条模拟请求。

用法：
  python3 deploy/webhook/selftest.py                 # 发一个被忽略的 ref，只验证签名链路
  python3 deploy/webhook/selftest.py --ref refs/heads/master   # 会真的触发 CI（谨慎）
  python3 deploy/webhook/selftest.py --dry-run       # 只打印将要发送的头，不发请求
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path("/etc/svquant/webhook.env")


def load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        data[k.strip()] = v.strip()
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="refs/heads/selftest-noop")
    ap.add_argument("--url", default="")
    ap.add_argument("--env", default=str(ENV_PATH))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    env_path = Path(args.env)
    if not env_path.is_file():
        print(f"找不到 {env_path}", file=sys.stderr)
        return 1
    env = load_env(env_path)
    secret = env.get("WEBHOOK_SECRET", "")
    port = env.get("WEBHOOK_PORT", "8788")
    if not secret:
        print("webhook.env 里没有 WEBHOOK_SECRET", file=sys.stderr)
        return 1

    url = args.url or f"http://127.0.0.1:{port}/hooks/gitee"
    ts = str(int(time.time() * 1000))
    mac = hmac.new(secret.encode(), f"{ts}\n{secret}".encode(), hashlib.sha256).digest()
    token = urllib.parse.quote_plus(base64.b64encode(mac))

    payload = {
        "hook_name": "push_hooks",
        "ref": args.ref,
        "before": "0" * 40,
        "after": "1" * 40,
        "created": False,
        "deleted": False,
        "repository": {"default_branch": "master"},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Gitee-Token": token,
        "X-Gitee-Timestamp": ts,
        "X-Gitee-Event": "Push Hook",
    }

    print(f"POST {url}  ref={args.ref}")
    if args.dry_run:
        print(json.dumps(headers, ensure_ascii=False, indent=2))
        return 0

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"HTTP {resp.status}: {resp.read().decode('utf-8', 'replace')}")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"连接失败：{e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
