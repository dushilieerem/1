# -*- coding: utf-8 -*-
"""因子面板指标缓存（PostgreSQL）+ 批跑 YGQuant 映射。"""
from __future__ import annotations

import json
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from typing import Any

import yaml

from services.factor.factor_verification_store import (
    LEGACY_LIBRARY_NAME,
    list_factor_verification_map,
    set_factor_verification_status,
)
from services.factor.factor_dashboard_metrics_store import (
    migrate_legacy_factor_dashboard_metrics,
)
from services.core.backtest_range import build_factor_backtest_payload
from services.core.db import get_conn
from services.core.re_config import RE_BASE

ROOT = Path(__file__).resolve().parents[2]
FACTOR_DIR = ROOT / "factor"
OUTPUT_DIR = ROOT / "output" / "factor_dashboard"
JOB_PATH = OUTPUT_DIR / "job.json"
RE_URL = f"{RE_BASE}/api/backtest/factor"
RULES_VERSION = "yg_v1"
# 与前端 detectComboCode.RE_BUILTIN_LIBS 对齐（含原 PLATFORM 五库）
RE_BUILTIN_LIBS = frozenset(
    {
        "emotion_indicators",
        "risk_indicators",
        "technical_indicators",
        "classic_indicators",
        "alpha_features",
        "momentum_lib",
        "value_lib",
        "technical_lib",
        "volatility_lib",
        "trading_lib",
        "alpha_library",
        "qlib_alpha",
        "jq_compat_technical",
        "jq_compat_risk",
        "jq_compat_emotion",
    }
)
# 面板批跑只允许这些官方库；禁止 custom_lib / 他人自定义
PANEL_OFFICIAL_LIBS = frozenset(
    {
        "momentum_lib",
        "value_lib",
        "technical_lib",
        "volatility_lib",
        "trading_lib",
        "emotion_indicators",
        "risk_indicators",
        "technical_indicators",
        "classic_indicators",
        "alpha_features",
    }
)

_job_lock = threading.Lock()
_job_thread: threading.Thread | None = None


def _ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _yg_get_json(path: str, timeout: int = 60) -> Any:
    from services.core.lan_http import urlopen_direct

    url = f"{RE_BASE.rstrip('/')}{path}"
    req = urllib.request.Request(url, method="GET")
    with urlopen_direct(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_factor_index(*, include_qlib: bool = True) -> list[dict]:
    """面板只跑官方公开库（PANEL_OFFICIAL_LIBS），目录来自 ResearchEngine。

    明确排除：
    - custom_lib（用户自定义）
    - 未在白名单内的其它库
    """
    try:
        payload = _yg_get_json("/api/factor-libraries")
    except Exception as e:
        raise RuntimeError(f"读取 RE 因子库目录失败: {e}") from e

    libraries = payload.get("libraries") or []
    out: list[dict] = []
    for lib in libraries:
        lib_key = str(lib.get("name") or "").strip()
        if not lib_key or lib_key not in PANEL_OFFICIAL_LIBS:
            continue
        if lib_key in ("qlib_alpha", "alpha_features") and not include_qlib:
            continue
        try:
            detail = _yg_get_json(f"/api/factors/{urllib.parse.quote(lib_key)}")
        except Exception as e:
            raise RuntimeError(f"读取 RE 因子列表失败 ({lib_key}): {e}") from e
        for f in detail.get("factors") or []:
            name = (f.get("name") or "").strip()
            if not name:
                continue
            out.append(
                {
                    "name": name,
                    "description": f.get("description") or name,
                    "library": lib_key,
                    "file": "",
                    "unavailable": False,
                    "unavailable_reason": "",
                }
            )
    return out


def _blank_metrics(*, error: str | None) -> dict:
    """失败/不可用：只写 error，数值一律置空，禁止编造。"""
    return {
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
        "error": (error or "")[:500] or None,
    }


def row_is_ok(
    *,
    factor_name: str,
    library: str | None,
    universe: str,
    period: str,
    filter_limit_up: bool,
    filter_suspended: bool,
) -> bool:
    migrate_legacy_factor_dashboard_metrics()
    with get_conn() as conn:
        r = conn.execute(
            """
            SELECT 1 FROM factor_dashboard_metrics
            WHERE factor_name=%s AND library=%s AND universe=%s AND period=%s
              AND filter_limit_up=%s AND filter_suspended=%s AND rules_version=%s
              AND error IS NULL AND ic_mean IS NOT NULL
            LIMIT 1
            """,
            (
                factor_name,
                str(library or ""),
                universe,
                period,
                1 if filter_limit_up else 0,
                1 if filter_suspended else 0,
                RULES_VERSION,
            ),
        ).fetchone()
    return r is not None


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
    from services.factor.re_backtest_bff import forward_factor_backtest

    return forward_factor_backtest(payload, timeout=timeout)


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


def prune_orphan_metrics(*, include_qlib: bool = True) -> dict:
    """删除不在当前官方目录中的面板缓存行（旧库改名/下线后的孤儿）。"""
    migrate_legacy_factor_dashboard_metrics()
    catalog = {
        (str(f.get("library") or ""), str(f["name"]))
        for f in load_factor_index(include_qlib=include_qlib)
    }
    with get_conn() as conn:
        existing = {
            (str(row["library"] or ""), str(row["factor_name"]))
            for row in conn.execute(
                "SELECT DISTINCT library, factor_name FROM factor_dashboard_metrics"
            ).fetchall()
        }
        orphans = sorted(existing - catalog)
        deleted = 0
        # 避免一次 DELETE 参数过多；用复合键精确清理下线/改名库中的缓存。
        chunk = 300
        for i in range(0, len(orphans), chunk):
            part = orphans[i : i + chunk]
            pairs = ", ".join("(%s, %s)" for _ in part)
            params = [value for pair in part for value in pair]
            cursor = conn.execute(
                f"DELETE FROM factor_dashboard_metrics WHERE (library, factor_name) IN ({pairs})",
                params,
            )
            deleted += max(cursor.rowcount, 0)
    return {
        "catalog": len(catalog),
        "orphan_names": len(orphans),
        "deleted_rows": deleted,
    }


def query_metrics(
    *,
    universe: str,
    period: str,
    filter_limit_up: bool,
    filter_suspended: bool,
    library: str | None = None,
) -> dict:
    migrate_legacy_factor_dashboard_metrics()
    catalog = {
        (str(f.get("library") or ""), str(f.get("name") or ""))
        for f in load_factor_index(include_qlib=True)
    }
    sql = """
      SELECT * FROM factor_dashboard_metrics
      WHERE universe=%s AND period=%s AND filter_limit_up=%s AND filter_suspended=%s
        AND rules_version=%s
    """
    args: list = [
        universe,
        period,
        1 if filter_limit_up else 0,
        1 if filter_suspended else 0,
        RULES_VERSION,
    ]
    if library:
        sql += " AND library=%s"
        args.append(library)
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    verify_map = list_factor_verification_map()
    # 只返回当前目录因子，避免旧缓存把「缓存因子」数撑到 1000+
    rows = [
        r
        for r in rows
        if (str(r.get("library") or ""), str(r.get("factor_name") or "")) in catalog
    ]
    for r in rows:
        if isinstance(r.get("computed_at"), datetime):
            r["computed_at"] = r["computed_at"].isoformat()
        name = str(r.get("factor_name") or "")
        library_name = str(r.get("library") or "")
        v = (
            verify_map.get((library_name, name))
            or verify_map.get((LEGACY_LIBRARY_NAME, name))
            or {}
        )
        r["verify_status"] = v.get("status") or "pending"
        r["verify_note"] = v.get("note") or ""
        r["verify_updated_at"] = v.get("updated_at") or ""
        r["verify_updated_by"] = v.get("updated_by") or ""
    pending = sum(1 for r in rows if r.get("verify_status") == "pending")
    passed = sum(1 for r in rows if r.get("verify_status") == "passed")
    failed = sum(1 for r in rows if r.get("verify_status") == "failed")
    return {
        "universe": universe,
        "period": period,
        "filter_limit_up": filter_limit_up,
        "filter_suspended": filter_suspended,
        "rules_version": RULES_VERSION,
        "count": len(rows),
        "rows": rows,
        "job": read_job(),
        "catalog_size": len(catalog),
        "verify_summary": {
            "pending": pending,
            "passed": passed,
            "failed": failed,
        },
        "note": "",
    }


def _fmt_ic(x: float | None) -> str | None:
    """面板 IC 按百分数点存：2.50 → 0.0250。"""
    if x is None:
        return None
    try:
        return f"{float(x) / 100.0:.4f}"
    except (TypeError, ValueError):
        return None


def _fmt_pct_from_panel(x: float | None) -> str | None:
    """面板库内存百分数点（如 33.07），展示为 +33.07%。"""
    if x is None:
        return None
    try:
        v = float(x)
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.2f}%"
    except (TypeError, ValueError):
        return None


def _fmt_num(x: float | None) -> str | None:
    if x is None:
        return None
    try:
        return f"{float(x):.2f}"
    except (TypeError, ValueError):
        return None


def lookup_panel_metric(
    *,
    factor_name: str,
    library: str | None = None,
    universe: str = "CSI300",
    period: str = "3y",
    filter_limit_up: bool = True,
    filter_suspended: bool = True,
) -> dict[str, Any] | None:
    """按因子×池×周期查面板缓存一行，组装成 platform_ref 形状。找不到返回 None。"""
    name = (factor_name or "").strip()
    uni = (universe or "CSI300").strip() or "CSI300"
    per = (period or "3y").strip() or "3y"
    if not name:
        return None
    migrate_legacy_factor_dashboard_metrics()
    sql = """
        SELECT * FROM factor_dashboard_metrics
        WHERE factor_name=%s AND universe=%s AND period=%s
          AND filter_limit_up=%s AND filter_suspended=%s AND rules_version=%s
    """
    params: list[Any] = [
        name,
        uni,
        per,
        1 if filter_limit_up else 0,
        1 if filter_suspended else 0,
        RULES_VERSION,
    ]
    if library:
        sql += " AND library=%s"
        params.append(library)
    sql += " ORDER BY computed_at DESC LIMIT 1"
    with get_conn() as conn:
        row = conn.execute(
            sql,
            params,
        ).fetchone()
    if not row:
        return None
    r = dict(row)
    if r.get("error"):
        return None
    display: dict[str, str] = {}
    put = lambda k, v: display.__setitem__(k, v) if v else None
    put("IC均值", _fmt_ic(r.get("ic_mean")))
    put("Rank IC", _fmt_ic(r.get("rank_ic")))
    put("IR", _fmt_num(r.get("ir")))
    put("年化", _fmt_pct_from_panel(r.get("annual_return")))
    put("最大回撤", _fmt_pct_from_panel(r.get("max_drawdown")))
    put("夏普", _fmt_num(r.get("sharpe")))
    wr = r.get("win_rate")
    if wr is None:
        wr = r.get("coverage_pool")
    put("胜率", _fmt_pct_from_panel(wr))
    put("Q1收益", _fmt_pct_from_panel(r.get("q1_return")))
    put("Q5收益", _fmt_pct_from_panel(r.get("q5_return")))
    put("多空价差", _fmt_pct_from_panel(r.get("long_short_spread")))
    put("Q1换手", _fmt_pct_from_panel(r.get("q1_turnover")))
    if not display:
        return None
    # metrics 用小数口径（与分享稿一致：面板百分数点 /100）
    def _div100(x: Any) -> float | None:
        if x is None:
            return None
        try:
            return float(x) / 100.0
        except (TypeError, ValueError):
            return None

    def _f(x: Any) -> float | None:
        if x is None:
            return None
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    name_cn = str(r.get("name_cn") or name)
    return {
        "source": "factor_panel",
        "label": f"因子面板 · {name_cn} · {uni} · {per}",
        "factor_name": name,
        "universe": uni,
        "period": per,
        "universe_code": uni,
        "period_code": per,
        "library": (str(r.get("library") or "").strip() or None),
        "filter_limit_up": bool(filter_limit_up),
        "metrics_display": display,
        "metrics": {
            k: v
            for k, v in {
                "ic_mean": _div100(r.get("ic_mean")),
                "rank_ic": _div100(r.get("rank_ic")),
                "ir": _f(r.get("ir")),
                "annual_return": _div100(r.get("annual_return")),
                "max_drawdown": _div100(r.get("max_drawdown")),
                "sharpe": _f(r.get("sharpe")),
                "win_rate": _div100(wr),
            }.items()
            if v is not None
        },
    }


def set_verify_status(
    *,
    factor_name: str,
    status: str,
    library_name: str | None = None,
    note: str = "",
    updated_by: str = "",
) -> dict:
    return set_factor_verification_status(
        factor_name=factor_name,
        status=status,
        library_name=library_name,
        note=note,
        updated_by=updated_by,
    )


def upsert_row(conn: Any, row: dict) -> None:
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
    key_cols = {
        "factor_name",
        "library",
        "universe",
        "period",
        "filter_limit_up",
        "filter_suspended",
        "rules_version",
    }
    placeholders = ",".join("%s" for _ in cols)
    updates = ",".join(
        f"{c}=EXCLUDED.{c}" for c in cols if c not in key_cols
    )
    values = [row.get(c) for c in cols]
    values[cols.index("library")] = str(row.get("library") or "")
    computed_at_index = cols.index("computed_at")
    values[computed_at_index] = _as_datetime(values[computed_at_index])
    conn.execute(
        f"""
        INSERT INTO factor_dashboard_metrics ({",".join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(factor_name, library, universe, period, filter_limit_up, filter_suspended, rules_version)
        DO UPDATE SET {updates}
        WHERE factor_dashboard_metrics.computed_at < EXCLUDED.computed_at
        """,
        values,
    )


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _store_metric(row: dict) -> None:
    with get_conn() as conn:
        upsert_row(conn, row)


def _run_batch(
    *,
    universe: str,
    period: str,
    filter_limit_up: bool,
    filter_suspended: bool,
    limit: int | None,
    only_names: list[str] | None = None,
    skip_ok: bool = False,
    analysis_level: str = "core",
    include_qlib: bool = True,
    libraries: list[str] | None = None,
) -> None:
    """批跑面板指标。

    - analysis_level 默认 core：面板所需 IC/分层/年化等标量均在 ResearchEngine API 契约中定义
    - skip_ok：已有成功行（无 error 且 ic_mean 非空）则跳过，保留旧结果
    - 失败只写 error + 空指标，不编造数字
    """
    factors = load_factor_index(include_qlib=include_qlib)
    if libraries:
        lib_set = set(libraries)
        factors = [f for f in factors if f.get("library") in lib_set]
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
            "filter_limit_up": filter_limit_up,
            "done": 0,
            "total": total,
            "skipped": 0,
            "failed": 0,
            "current": None,
            "analysis_level": analysis_level,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }
    )
    skipped = 0
    failed = 0
    try:
        migrate_legacy_factor_dashboard_metrics()
        for i, f in enumerate(factors):
            name = f["name"]
            write_job(
                {
                    "status": "running",
                    "universe": universe,
                    "period": period,
                    "filter_limit_up": filter_limit_up,
                    "done": i,
                    "total": total,
                    "skipped": skipped,
                    "failed": failed,
                    "current": name,
                    "analysis_level": analysis_level,
                    "started_at": read_job().get("started_at"),
                    "error": None,
                }
            )
            base = {
                "factor_name": name,
                "universe": universe,
                "period": period,
                "filter_limit_up": 1 if filter_limit_up else 0,
                "filter_suspended": 1 if filter_suspended else 0,
                "rules_version": RULES_VERSION,
                "name_cn": f.get("description"),
                "library": f.get("library"),
                "computed_at": datetime.now(timezone.utc),
            }
            try:
                if f.get("unavailable"):
                    reason = (f.get("unavailable_reason") or "数据不可用").strip()
                    _store_metric({**base, **_blank_metrics(error=reason)})
                    failed += 1
                    time.sleep(0.02)
                    continue

                if skip_ok and row_is_ok(
                    factor_name=name,
                    library=f.get("library"),
                    universe=universe,
                    period=period,
                    filter_limit_up=filter_limit_up,
                    filter_suspended=filter_suspended,
                ):
                    skipped += 1
                    continue

                lib_key = (f.get("library") or "").strip()
                # 官方库一律 library_name；不再读本地 .py
                if lib_key in RE_BUILTIN_LIBS or lib_key in PANEL_OFFICIAL_LIBS:
                    data = call_yg_backtest(
                        build_factor_backtest_payload(
                            factor_name=name,
                            library_name=lib_key,
                            universe=universe,
                            period=period,
                            filter_limit_up=filter_limit_up,
                            filter_suspended=filter_suspended,
                            analysis_level=analysis_level,
                        )
                    )
                else:
                    raise RuntimeError(
                        f"面板不支持非官方库因子: {lib_key or '?'} / {name}"
                    )
                mapped = map_yg_response(data)
                if mapped.get("error"):
                    # RE 业务错误：只记原因，清空数值
                    _store_metric({**base, **_blank_metrics(error=str(mapped["error"]))})
                    failed += 1
                else:
                    _store_metric({**base, **mapped})
            except Exception as exc:
                traceback.print_exc()
                _store_metric({**base, **_blank_metrics(error=str(exc))})
                failed += 1
            time.sleep(0.15)
        write_job(
            {
                "status": "done",
                "universe": universe,
                "period": period,
                "filter_limit_up": filter_limit_up,
                "done": total,
                "total": total,
                "skipped": skipped,
                "failed": failed,
                "current": None,
                "analysis_level": analysis_level,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
            }
        )
    except Exception as exc:
        write_job({**read_job(), "status": "failed", "error": str(exc)})


def start_refresh(
    *,
    universe: str = "CSI300",
    period: str = "3y",
    filter_limit_up: bool = True,
    filter_suspended: bool = True,
    limit: int | None = None,
    skip_ok: bool = True,
    analysis_level: str = "core",
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
                "skip_ok": skip_ok,
                "analysis_level": analysis_level,
            },
            daemon=True,
        )
        _job_thread = t
        t.start()
    return {"ok": True, "job": read_job()}
