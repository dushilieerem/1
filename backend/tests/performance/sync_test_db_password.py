# -*- coding: utf-8 -*-
"""Synchronize the local test PostgreSQL user's password with backend/.env.

This script is for the local R4 TEST database only. It does not print the password.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    raw = (ROOT / ".env").read_text(encoding="utf-8-sig", errors="ignore")
    url = ""
    for line in raw.splitlines():
        if line.strip().startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
    parsed = urlparse(url)
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    if user != "svquant" or not password:
        raise SystemExit("DATABASE_URL user/password is not usable for local test sync")
    sql = "ALTER ROLE svquant PASSWORD '" + password.replace("'", "''") + "';\n"
    subprocess.run(
        ["docker", "exec", "-i", "svquant-postgres", "psql", "-U", "svquant", "-d", "svquant", "-q"],
        input=sql.encode("utf-8"),
        check=True,
    )
    print("database password synchronized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
