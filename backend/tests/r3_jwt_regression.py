# -*- coding: utf-8 -*-
"""R3 JWT security fix regression suite.

Run while backend is listening on R3_BASE/CONTRACT_BASE with a strong JWT_SECRET_KEY.
The suite redacts reusable tokens and secrets from its JSON artifact.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.auth.auth_store import ensure_schema, hash_password  # noqa: E402
from services.core.db import get_conn  # noqa: E402

BASE = (os.environ.get("R3_BASE") or os.environ.get("CONTRACT_BASE") or "http://127.0.0.1:8766").rstrip("/")
RUN_ID = os.environ.get("R3_FIX_RUN_ID") or f"R3_FIX_{int(time.time())}"

SENSITIVE_RE = re.compile(
    r"(jwt_secret_key|jwt_secret|api[_-]?key|access_token|authorization|bearer\s+[a-z0-9._-]+|eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+|postgresql://[^@\s]+@)",
    re.I,
)


@dataclass
class Result:
    case_id: str
    title: str
    status: str
    expected: str
    actual: str
    http_status: int | None = None


RESULTS: list[Result] = []


def redact(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, default=str)
    return SENSITIVE_RE.sub("[REDACTED]", raw)[:800]


def record(case_id: str, title: str, ok: bool, *, expected: str, actual: Any, http_status: int | None = None) -> None:
    RESULTS.append(Result(case_id, title, "PASS" if ok else "FAIL", expected, redact(actual), http_status))


def req(method: str, path: str, *, token: str | None = None, body: dict | None = None) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json", "User-Agent": f"SVQuant-R3-Fix/{RUN_ID}"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed
    except Exception as exc:
        return 0, {"error": str(exc)}


def ensure_user(username: str, password: str, *, role: str) -> int:
    ensure_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO users (username, email, password_hash, role, status, display_name)
            VALUES (%s, %s, %s, %s, 'active', %s)
            ON CONFLICT (username) DO UPDATE SET
              password_hash = EXCLUDED.password_hash,
              role = EXCLUDED.role,
              status = 'active',
              display_name = EXCLUDED.display_name,
              updated_at = NOW()
            RETURNING id
            """,
            (username, None, hash_password(password), role, username),
        ).fetchone()
    return int(row["id"])


def cleanup(*names: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE username = ANY(%s)", (list(names),))


def login(username: str, password: str) -> str | None:
    status, data = req("POST", "/api/auth/login", body={"username": username, "password": password})
    if status == 200 and isinstance(data, dict):
        return data.get("token")
    return None


def sign_token(secret: str, user_id: int, username: str, role: str = "admin") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "username": username,
            "role": role,
            "permission": "admin",
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        secret,
        algorithm="HS256",
    )


def tamper_payload(token: str) -> str:
    parts = token.split(".")
    if len(parts) != 3:
        return token + "x"
    return parts[0] + "." + parts[1][::-1] + "." + parts[2]


def case_missing_secret_fails_fast() -> None:
    env = os.environ.copy()
    env["JWT_SECRET_KEY"] = ""
    code = (
        "import sys; "
        "sys.path.insert(0, r'{}'); "
        "from services.auth.auth_store import validate_auth_config; "
        "validate_auth_config()"
    ).format(str(ROOT))
    proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
    record(
        "TC-SEC-JWT-REGRESSION-001",
        "missing JWT_SECRET_KEY fails fast",
        proc.returncode != 0,
        expected="non-zero startup/config validation failure",
        actual={"returncode": proc.returncode},
    )


def main() -> int:
    secret = (os.environ.get("JWT_SECRET_KEY") or "").strip()
    if not secret:
        raise SystemExit("JWT_SECRET_KEY is required for regression run")

    case_missing_secret_fails_fast()

    admin_name = f"{RUN_ID}_admin"
    user_name = f"{RUN_ID}_user"
    admin_password = "Aa123456!"
    user_password = "Bb123456!"
    admin_id = ensure_user(admin_name, admin_password, role="admin")
    user_id = ensure_user(user_name, user_password, role="user")
    try:
        old_default = sign_token("svquant-dev-jwt-secret-change-me", admin_id, admin_name)
        status, data = req("GET", "/api/admin/logs?limit=1", token=old_default)
        record("TC-SEC-JWT-REGRESSION-002", "old default secret token is rejected", status in {401, 403}, expected="401/403", actual=data, http_status=status)

        wrong = sign_token("wrong-secret-for-r3-regression-000000", admin_id, admin_name)
        status, data = req("GET", "/api/admin/logs?limit=1", token=wrong)
        record("TC-SEC-JWT-REGRESSION-003", "random wrong secret token is rejected", status in {401, 403}, expected="401/403", actual=data, http_status=status)

        correct = sign_token(secret, admin_id, admin_name)
        status, data = req("GET", "/api/admin/logs?limit=1", token=correct)
        record("TC-SEC-JWT-REGRESSION-004", "correct environment secret token is accepted", status == 200, expected="200", actual={"ok": status == 200}, http_status=status)

        user_token = login(user_name, user_password)
        status, data = req("GET", "/api/admin/logs?limit=1", token=tamper_payload(user_token or ""))
        record("TC-SEC-JWT-REGRESSION-005", "tampered payload token is rejected", status in {401, 403}, expected="401/403", actual=data, http_status=status)

        elevated = sign_token("wrong-secret-for-r3-regression-000000", user_id, user_name, role="admin")
        status, data = req("GET", "/api/admin/logs?limit=1", token=elevated)
        record("TC-SEC-JWT-REGRESSION-006", "role escalation token signed with wrong secret is rejected", status in {401, 403}, expected="401/403", actual=data, http_status=status)
    finally:
        cleanup(admin_name, user_name)

    summary = {
        "total": len(RESULTS),
        "passed": sum(1 for r in RESULTS if r.status == "PASS"),
        "failed": sum(1 for r in RESULTS if r.status == "FAIL"),
        "blocked": 0,
    }
    out = {"run_id": RUN_ID, "summary": summary, "results": [asdict(r) for r in RESULTS]}
    path = Path(__file__).with_name(f"{RUN_ID}_jwt_regression_results.json")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print(str(path))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
