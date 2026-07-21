# -*- coding: utf-8 -*-
"""因子面板指标缓存（SQLite）+ 批跑 YGQuant 映射。"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

from services.backtest_range import build_factor_backtest_payload

ROOT = Path(__file__).resolve().parents[1]
FACTOR_DIR = ROOT / "factor"
OUTPUT_DIR = ROOT / "output" / "factor_dashboard"
DB_PATH = OUTPUT_DIR / "metrics.sqlite"
JOB_PATH = OUTPUT_DIR / "job.json"
RE_URL = "http://192.168.3.64:9527/api/backtest/factor"
RULES_VERSION = "yg_v1"

_job_lock = threading.Lock()
_job_thread: threading.Thread | None = None


def _ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _migrate_columns(conn: sqlite3.Connection) -> None:
    existing = {r[1] for r in conn.execute("PRAGMA table_info(factor_dashboard_metrics)")}
    for col, typ in (
        ("rank_ic", "REAL"),
        ("win_rate", "REAL"),
        ("volatility", "REAL"),
    ):
        if col not in existing:
            conn.execute(f"ALTER TABLE factor_dashboard_metrics ADD COLUMN {col} {typ}")


def _connect() -> sqlite3.Connection:
    _ensure_dirs()
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS factor_dashboard_metrics (
          factor_name TEXT NOT NULL,
          universe TEXT NOT NULL,
          period TEXT NOT NULL,
          filter_limit_up INTEGER NOT NULL,
          filter_suspended INTEGER NOT NULL,
          rules_version TEXT NOT NULL DEFAULT 'yg_v1',
          name_cn TEXT,
          library TEXT,
          ic_mean REAL,
          ic_std REAL,
          ir REAL,
          q1_return REAL,
          q5_return REAL,
          long_short_spread REAL,
          q1_turnover REAL,
          q5_turnover REAL,
          coverage_pool REAL,
          coverage_total REAL,
          sharpe REAL,
          annual_return REAL,
          max_drawdown REAL,
          rank_ic REAL,
          win_rate REAL,
          volatility REAL,
          error TEXT,
          computed_at TEXT NOT NULL,
          PRIMARY KEY (
            factor_name, universe, period,
            filter_limit_up, filter_suspended, rules_version
          )
        )
        """
    )
    _migrate_columns(conn)
    conn.commit()
    return conn


def load_factor_index() -> list[dict]:
    """面板只跑官方库；跳过 custom_lib / 带 owner_id 的私有因子。"""
    raw = yaml.safe_load((FACTOR_DIR / "index.yaml").read_text(encoding="utf-8")) or {}
    out: list[dict] = []
    for lib_key, lib in (raw.get("libraries") or {}).items():
        if lib_key == "custom_lib":
            continue
        for f in lib.get("factors") or []:
            if f.get("owner_id") is not None:
                continue
            out.append(
                {
                    "name": f.get("name"),
                    "description": f.get("description") or f.get("name"),
                    "library": lib_key,
                    "file": lib.get("file"),
                    "unavailable": bool(f.get("unavailable")),
                    "unavailable_reason": f.get("unavailable_reason") or "",
                }
            )
    return [x for x in out if x.get("name")]


def extract_method(source: str, method_name: str) -> str:
    lines = source.splitlines()
    start = -1
    indent = ""
    import re

    for i, line in enumerate(lines):
        m = re.match(rf"^(\s*)def\s+{re.escape(method_name)}\s*\(", line)
        if m:
            start = i
            indent = m.group(1)
            break
    if start < 0:
        raise KeyError(method_name)
    out = [lines[start]]
    body_indent = indent + "    "
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            out.append(line)
            continue
        if line.startswith(body_indent):
            out.append(line)
            continue
        if line.startswith(indent) and re.match(r"^(def|class)\s+", line[len(indent) :]):
            break
        if not line.startswith(indent):
            break
        out.append(line)
    n = len(indent)
    return "\n".join(ln[n:] if len(ln) >= n else ln for ln in out).strip()


def _pct100(x) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    # RE 多为小数；若已像百分数（|v|>1.5 且像百分比）则不再 ×100
    if abs(v) <= 1.5:
        return round(v * 100, 4)
    return round(v, 4)


def map_yg_response(data: dict) -> dict:
    fa = data.get("factor_analysis") or {}
    lr = fa.get("layered_returns") or {}
    if not isinstance(lr, dict):
        lr = {}
    metrics = data.get("metrics") or {}
    ic = fa.get("ic_mean")
    if ic is None:
        ic = metrics.get("ic")
    rank_ic = fa.get("rank_ic_mean")
    if rank_ic is None:
        rank_ic = metrics.get("rank_ic")
    ic_std = fa.get("ic_std")
    ic_mean = _pct100(ic)
    ic_std_pct = _pct100(ic_std) if ic_std is not None else None
    ir = None
    if ic is not None and ic_std not in (None, 0):
        try:
            ir = round(float(ic) / float(ic_std), 4)
        except (TypeError, ValueError, ZeroDivisionError):
            ir = None

    q1 = _pct100(lr.get("layer1"))
    q5 = _pct100(lr.get("layer5"))
    # core 在部分股票池不返回 layered_returns；用分组净值末值推区间收益
    if q1 is None or q5 is None:
        series = fa.get("cumulative_series") or []
        if series:
            last = series[-1] if isinstance(series[-1], dict) else {}
            if q1 is None and last.get("layer1") is not None:
                try:
                    q1 = _pct100(float(last["layer1"]) - 1.0)
                except (TypeError, ValueError):
                    pass
            if q5 is None and last.get("layer5") is not None:
                try:
                    q5 = _pct100(float(last["layer5"]) - 1.0)
                except (TypeError, ValueError):
                    pass

    spread = _pct100(lr.get("spread"))
    if spread is None:
        spread = _pct100(lr.get("long_short_return"))
    if spread is None and q1 is not None and q5 is not None:
        spread = round(q5 - q1, 4)

    turnover = _pct100(metrics.get("turnover"))
    win_rate = _pct100(metrics.get("win_rate"))
    vol = _pct100(metrics.get("volatility"))
    err = data.get("error")
    return {
        "ic_mean": ic_mean,
        "ic_std": ic_std_pct,
        "ir": ir,
        "rank_ic": _pct100(rank_ic),
        "q1_return": q1,
        "q5_return": q5,
        "long_short_spread": spread,
        "q1_turnover": turnover,
        "q5_turnover": None,
        "coverage_pool": None,
        "coverage_total": None,
        "win_rate": win_rate,
        "volatility": vol,
        "sharpe": metrics.get("sharpe"),
        "annual_return": _pct100(metrics.get("annual_return")),
        "max_drawdown": _pct100(metrics.get("max_drawdown")),
        "error": err if err else None,
    }


def call_yg_backtest(payload: dict, timeout: int = 600) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        RE_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"HTTP Error {exc.code}: {exc.reason}" + (f" | {detail}" if detail else "")) from exc


def read_job() -> dict:
    _ensure_dirs()
    if not JOB_PATH.exists():
        return {"status": "idle"}
    try:
        return json.loads(JOB_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "idle"}


def write_job(data: dict) -> None:
    _ensure_dirs()
    tmp = JOB_PATH.with_suffix(".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    last_exc: Exception | None = None
    for attempt in range(8):
        try:
            tmp.write_text(payload, encoding="utf-8")
            try:
                tmp.replace(JOB_PATH)
            except PermissionError:
                # Windows 上目标文件偶发被占用：先删再替换
                if JOB_PATH.exists():
                    JOB_PATH.unlink(missing_ok=True)
                tmp.replace(JOB_PATH)
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(0.05 * (attempt + 1))
    if last_exc:
        raise last_exc


def query_metrics(
    *,
    universe: str,
    period: str,
    filter_limit_up: bool,
    filter_suspended: bool,
    library: str | None = None,
) -> dict:
    conn = _connect()
    sql = """
      SELECT * FROM factor_dashboard_metrics
      WHERE universe=? AND period=? AND filter_limit_up=? AND filter_suspended=?
        AND rules_version=?
    """
    args: list = [
        universe,
        period,
        1 if filter_limit_up else 0,
        1 if filter_suspended else 0,
        RULES_VERSION,
    ]
    if library:
        sql += " AND library=?"
        args.append(library)
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close()
    return {
        "universe": universe,
        "period": period,
        "filter_limit_up": filter_limit_up,
        "filter_suspended": filter_suspended,
        "rules_version": RULES_VERSION,
        "count": len(rows),
        "rows": rows,
        "job": read_job(),
        "note": "",
    }


def upsert_row(conn: sqlite3.Connection, row: dict) -> None:
    cols = [
        "factor_name",
        "universe",
        "period",
        "filter_limit_up",
        "filter_suspended",
        "rules_version",
        "name_cn",
        "library",
        "ic_mean",
        "ic_std",
        "ir",
        "rank_ic",
        "q1_return",
        "q5_return",
        "long_short_spread",
        "q1_turnover",
        "q5_turnover",
        "coverage_pool",
        "coverage_total",
        "win_rate",
        "volatility",
        "sharpe",
        "annual_return",
        "max_drawdown",
        "error",
        "computed_at",
    ]
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in {
        "factor_name",
        "universe",
        "period",
        "filter_limit_up",
        "filter_suspended",
        "rules_version",
    })
    conn.execute(
        f"""
        INSERT INTO factor_dashboard_metrics ({",".join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(factor_name, universe, period, filter_limit_up, filter_suspended, rules_version)
        DO UPDATE SET {updates}
        """,
        [row.get(c) for c in cols],
    )


def _run_batch(
    *,
    universe: str,
    period: str,
    filter_limit_up: bool,
    filter_suspended: bool,
    limit: int | None,
    only_names: list[str] | None = None,
) -> None:
    factors = load_factor_index()
    if only_names:
        want = set(only_names)
        factors = [f for f in factors if f["name"] in want]
    if limit:
        factors = factors[:limit]
    total = len(factors)
    write_job(
        {
            "status": "running",
            "universe": universe,
            "period": period,
            "done": 0,
            "total": total,
            "current": None,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }
    )
    conn = _connect()
    try:
        for i, f in enumerate(factors):
            name = f["name"]
            write_job(
                {
                    "status": "running",
                    "universe": universe,
                    "period": period,
                    "done": i,
                    "total": total,
                    "current": name,
                    "started_at": read_job().get("started_at"),
                    "error": None,
                }
            )
            py_path = FACTOR_DIR / (f.get("file") or "")
            now = datetime.now(timezone.utc).isoformat()
            base = {
                "factor_name": name,
                "universe": universe,
                "period": period,
                "filter_limit_up": 1 if filter_limit_up else 0,
                "filter_suspended": 1 if filter_suspended else 0,
                "rules_version": RULES_VERSION,
                "name_cn": f.get("description"),
                "library": f.get("library"),
                "computed_at": now,
            }
            try:
                if f.get("unavailable"):
                    reason = (f.get("unavailable_reason") or "数据不可用").strip()
                    upsert_row(
                        conn,
                        {
                            **base,
                            "ic_mean": None,
                            "ic_std": None,
                            "ir": None,
                            "rank_ic": None,
                            "q1_return": None,
                            "q5_return": None,
                            "long_short_spread": None,
                            "q1_turnover": None,
                            "q5_turnover": None,
                            "coverage_pool": None,
                            "coverage_total": None,
                            "win_rate": None,
                            "volatility": None,
                            "sharpe": None,
                            "annual_return": None,
                            "max_drawdown": None,
                            "error": reason[:500],
                        },
                    )
                    conn.commit()
                    time.sleep(0.05)
                    continue
                if not py_path.exists():
                    raise FileNotFoundError(str(py_path))
                code = extract_method(py_path.read_text(encoding="utf-8"), name)
                data = call_yg_backtest(
                    build_factor_backtest_payload(
                        factor_code=code,
                        factor_name=name,
                        universe=universe,
                        period=period,
                        filter_limit_up=filter_limit_up,
                        filter_suspended=filter_suspended,
                        # 部分股票池在 core 下不返回 factor_analysis/分层，面板必须用 full
                        analysis_level="full",
                    )
                )
                mapped = map_yg_response(data)
                upsert_row(conn, {**base, **mapped})
            except Exception as exc:
                traceback.print_exc()
                upsert_row(
                    conn,
                    {
                        **base,
                        "ic_mean": None,
                        "ic_std": None,
                        "ir": None,
                        "rank_ic": None,
                        "q1_return": None,
                        "q5_return": None,
                        "long_short_spread": None,
                        "q1_turnover": None,
                        "q5_turnover": None,
                        "coverage_pool": None,
                        "coverage_total": None,
                        "win_rate": None,
                        "volatility": None,
                        "sharpe": None,
                        "annual_return": None,
                        "max_drawdown": None,
                        "error": str(exc)[:500],
                    },
                )
            conn.commit()
            time.sleep(0.2)
        write_job(
            {
                "status": "done",
                "universe": universe,
                "period": period,
                "done": total,
                "total": total,
                "current": None,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
            }
        )
    except Exception as exc:
        write_job({**read_job(), "status": "failed", "error": str(exc)})
    finally:
        conn.close()


def start_refresh(
    *,
    universe: str = "CSI300",
    period: str = "3y",
    filter_limit_up: bool = True,
    filter_suspended: bool = True,
    limit: int | None = None,
) -> dict:
    global _job_thread
    with _job_lock:
        job = read_job()
        if job.get("status") == "running" and _job_thread and _job_thread.is_alive():
            return {"ok": False, "error": "已有任务在跑", "job": job}
        t = threading.Thread(
            target=_run_batch,
            kwargs={
                "universe": universe,
                "period": period,
                "filter_limit_up": filter_limit_up,
                "filter_suspended": filter_suspended,
                "limit": limit,
            },
            daemon=True,
        )
        _job_thread = t
        t.start()
    return {"ok": True, "job": read_job()}
