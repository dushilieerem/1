# -*- coding: utf-8 -*-
"""??? HTTP????? HTTP_PROXY?Clash ????? 192.168.x ??? 502?"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def ensure_lan_no_proxy(*hosts: str) -> None:
    """???????? NO_PROXY / no_proxy????????"""
    extras = [h.strip() for h in hosts if h and h.strip()]
    extras += ["192.168.3.64", "127.0.0.1", "localhost"]
    for key in ("NO_PROXY", "no_proxy"):
        cur = [x.strip() for x in (os.environ.get(key) or "").split(",") if x.strip()]
        merged = list(dict.fromkeys([*cur, *extras]))
        os.environ[key] = ",".join(merged)


# ???????????? urllib ????????
ensure_lan_no_proxy()

_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def urlopen_direct(req: urllib.request.Request, timeout: float | int = 60):
    """??????? urlopen?"""
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


def post_json_with_status(
    url: str, payload: dict[str, Any], *, timeout: float | int = 600
) -> tuple[int, Any]:
    """POST JSON??? (status_code, body)?202 Accepted ?????"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen_direct(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw.strip() else {}
            return int(getattr(resp, "status", 200) or 200), data
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        raise RuntimeError(
            f"HTTP Error {exc.code}: {exc.reason}" + (f" | {detail}" if detail else "")
        ) from exc


def post_json(url: str, payload: dict[str, Any], *, timeout: float | int = 600) -> dict[str, Any]:
    status, data = post_json_with_status(url, payload, timeout=timeout)
    if not isinstance(data, dict):
        raise RuntimeError(f"HTTP {status}: ??? JSON ??")
    return data


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float | int = 120,
) -> tuple[int, dict[str, str], Any]:
    """?????? JSON??? (status, headers_lower, body)?

    4xx/5xx ??? status+body??????? BFF ??????
    """
    data_bytes = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method.upper())
    try:
        with urlopen_direct(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            body: Any = json.loads(raw) if raw.strip() else {}
            hdrs = {
                str(k).lower(): str(v)
                for k, v in (resp.headers.items() if resp.headers else [])
            }
            return int(getattr(resp, "status", 200) or 200), hdrs, body
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        body: Any = {}
        if raw.strip():
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"error": raw[:500]}
        hdrs = {
            str(k).lower(): str(v)
            for k, v in (exc.headers.items() if exc.headers else [])
        }
        return int(exc.code), hdrs, body
    except urllib.error.URLError as exc:
        return 502, {}, {"error": f"????????{exc.reason}"}
