"""Small auth adapter for the demo H5.

Two modes:
- demo (default): `demo / demo1234` issues a local Invest session token.
- svquant: if `SVQUANT_API_BASE` is set, credentials are checked against the
  existing SVQuant `/api/auth/login`; on success the H5 gets its own short-lived
  Invest token for the same user.  This reuses the account without copying the
  password hash or the SVQuant signing key.

The token format is a minimal HS256 JWT so we do not need PyJWT in the demo
environment.  For production, set `INVEST_JWT_SECRET` to a strong secret.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

SECRET = (os.getenv("INVEST_JWT_SECRET") or "invest-dev-secret-change-me-32-chars").encode()
ISSUER = "svquant-invest"
DEFAULT_TTL = 7 * 24 * 3600
SVQUANT_BASE = (os.getenv("SVQUANT_API_BASE") or "").rstrip("/")
DEMO_USER = {"id": 1, "username": "demo", "display_name": "演示用户", "role": "user", "status": "active"}


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def _sign(message: bytes) -> bytes:
    return hmac.new(SECRET, message, hashlib.sha256).digest()


def issue_token(user: dict[str, Any], ttl: int = DEFAULT_TTL) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": str(user.get("id") or user.get("username") or "demo"),
        "username": user.get("username") or "demo",
        "display_name": user.get("display_name") or user.get("username") or "演示用户",
        "role": user.get("role") or "user",
        "iss": ISSUER,
        "iat": now,
        "exp": now + ttl,
    }
    head = _b64e(json.dumps(header, separators=(",", ":")).encode())
    body = _b64e(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    signature = _b64e(_sign(f"{head}.{body}".encode()))
    return f"{head}.{body}.{signature}"


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        head, body, signature = token.split(".")
        expected = _sign(f"{head}.{body}".encode())
        if not hmac.compare_digest(expected, _b64d(signature)):
            return None
        payload = json.loads(_b64d(body))
        if payload.get("exp", 0) < int(time.time()):
            return None
        if payload.get("iss") != ISSUER:
            return None
        return payload
    except Exception:
        return None


def user_from_authorization(header: str | None) -> dict[str, Any] | None:
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    payload = decode_token(parts[1].strip())
    if not payload:
        return None
    return {
        "id": int(payload.get("sub") or 0),
        "username": payload.get("username") or "demo",
        "display_name": payload.get("display_name") or payload.get("username") or "演示用户",
        "role": payload.get("role") or "user",
        "status": "active",
    }


def _proxy_login(username: str, password: str) -> dict[str, Any]:
    body = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        f"{SVQUANT_BASE}/api/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = "账号或密码错误"
        try:
            detail = json.loads(exc.read().decode()).get("detail") or detail
        except Exception:
            pass
        raise ValueError(detail) from exc
    except Exception as exc:
        raise ValueError("主站登录服务暂不可用，请使用演示账号") from exc
    user = data.get("user") or {}
    if not user.get("username"):
        raise ValueError("主站登录响应异常")
    return {
        "id": user.get("id") or 0,
        "username": user["username"],
        "display_name": user.get("display_name") or user["username"],
        "role": user.get("role") or "user",
        "status": user.get("status") or "active",
    }


def _proxy_register(username: str, password: str, email: str | None, display_name: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"username": username, "password": password}
    if email:
        payload["email"] = email
    if display_name:
        payload["display_name"] = display_name
    req = urllib.request.Request(
        f"{SVQUANT_BASE}/api/auth/register",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = "注册失败"
        try:
            detail = json.loads(exc.read().decode()).get("detail") or detail
        except Exception:
            pass
        raise ValueError(detail) from exc
    except Exception as exc:
        raise ValueError("主站注册服务暂不可用") from exc
    user = data.get("user") or {}
    if not user.get("username"):
        raise ValueError("主站注册响应异常")
    return {
        "id": user.get("id") or 0,
        "username": user["username"],
        "display_name": user.get("display_name") or user["username"],
        "role": user.get("role") or "user",
        "status": user.get("status") or "active",
    }


def login(username: str, password: str) -> dict[str, Any]:
    username = (username or "").strip()
    if username == "demo" and password == "demo1234":
        return {"token": issue_token(DEMO_USER), "user": DEMO_USER, "mode": "demo"}
    if SVQUANT_BASE:
        user = _proxy_login(username, password)
        if user.get("status") != "active":
            raise ValueError("账号已停用")
        return {"token": issue_token(user), "user": user, "mode": "svquant"}
    raise ValueError("账号或密码错误；演示环境请用 demo / demo1234")


def register(username: str, password: str, email: str | None = None,
             display_name: str | None = None) -> dict[str, Any]:
    username = (username or "").strip()
    display_name = (display_name or "").strip() or username
    if not SVQUANT_BASE:
        raise ValueError("演示环境不开放注册；请到 SVQuant 主站注册后再登录")
    user = _proxy_register(username, password, (email or "").strip() or None, display_name)
    if user.get("status") != "active":
        raise ValueError("账号已停用")
    return {"token": issue_token(user), "user": user, "mode": "svquant"}


def sso(token: str) -> dict[str, Any]:
    """Exchange a main-site SVQuant token for an Invest token.

    The main site can redirect to `#svq_token=...` (fragment, not sent to the
    server).  H5 removes the fragment immediately after exchange.  This is not
    cookie SSO; it still requires the main site to hand off a token.
    """
    if not SVQUANT_BASE:
        raise ValueError("演示环境不支持主站 SSO")
    token = (token or "").strip()
    if not token:
        raise ValueError("缺少主站 token")
    req = urllib.request.Request(
        f"{SVQUANT_BASE}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise ValueError("主站登录已失效，请重新登录") from exc
    except Exception as exc:
        raise ValueError("主站鉴权服务暂不可用") from exc
    user = data.get("user") or {}
    if not user.get("username"):
        raise ValueError("主站鉴权响应异常")
    normalized = {
        "id": user.get("id") or 0,
        "username": user["username"],
        "display_name": user.get("display_name") or user["username"],
        "role": user.get("role") or "user",
        "status": user.get("status") or "active",
    }
    if normalized["status"] != "active":
        raise ValueError("账号已停用")
    return {"token": issue_token(normalized), "user": normalized, "mode": "svquant-sso"}
