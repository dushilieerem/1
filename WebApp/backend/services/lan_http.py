# -*- coding: utf-8 -*-
"""局域网 HTTP：绕过本机 HTTP_PROXY（Clash 等），避免 192.168.x 被拐成 502。"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def ensure_lan_no_proxy(*hosts: str) -> None:
    """把局域网主机并入 NO_PROXY / no_proxy（进程内生效）。"""
    extras = [h.strip() for h in hosts if h and h.strip()]
    extras += ["192.168.3.64", "127.0.0.1", "localhost"]
    for key in ("NO_PROXY", "no_proxy"):
        cur = [x.strip() for x in (os.environ.get(key) or "").split(",") if x.strip()]
        merged = list(dict.fromkeys([*cur, *extras]))
        os.environ[key] = ",".join(merged)


# 模块导入即生效，覆盖后续 urllib 默认走代理的行为
ensure_lan_no_proxy()

_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def urlopen_direct(req: urllib.request.Request, timeout: float | int = 60):
    """不走系统代理的 urlopen。"""
    return _DIRECT.open(req, timeout=timeout)


def get_json(url: str, *, timeout: float | int = 60) -> Any:
    req = urllib.request.Request(url, method="GET")
    try:
        with urlopen_direct(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        raise RuntimeError(
            f"HTTP Error {exc.code}: {exc.reason}" + (f" | {detail}" if detail else "")
        ) from exc


def post_json(url: str, payload: dict[str, Any], *, timeout: float | int = 600) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen_direct(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        raise RuntimeError(
            f"HTTP Error {exc.code}: {exc.reason}" + (f" | {detail}" if detail else "")
        ) from exc
