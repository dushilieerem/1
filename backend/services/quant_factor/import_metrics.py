"""AC-08a import-benchmark-v1 metrics batch (PM-V5-019).

The batch never fabricates metrics. A row becomes ``ok`` only when RE returns a
real daily Rank IC series, a verifiable long-leg turnover and the NW t computed
from that same series. Missing R1 / missing turnover stay ``pending`` with a
reason; explicit definition/PIT failures become ``not_computable``.
"""
from __future__ import annotations

import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from services.core.db import get_conn
from services.factor.re_factor_async_proxy import proxy_get_factor_run, proxy_submit_factor_backtest
from services.workflow_workspace.platform_data import published_view

from .metrics import newey_west_t

BENCHMARK_VERSION = "import-benchmark-v1"
PARAMS = {
    "benchmark_version": BENCHMARK_VERSION,
    "universe": "CSI300",
    "benchmark": "CSI300",
    "start": "2022-01-01",
    "end": "2024-12-31",
    "holding_period": 1,
    "execution_timing": "next_open",
    "groups": 5,
    "rebalance_days": 1,
    "direction": "raw",
    "analysis_level": "full",
    "commission_rate": 0.0003,
    "stamp_tax": 0.0005,
    "slippage_rate": 0.0005,
}
POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quant-import-metrics")
WORKERS = 2
_POLL_SECONDS = 900


def view_snapshot() -> dict:
    view = published_view()
    datasets = view.get("datasets") or {}
    release_ids = {name: entry.get("release") for name, entry in datasets.items() if entry.get("release")}
    dates = [entry.get("date_max") for entry in datasets.values() if entry.get("date_max")]
    return {
        "view_id": view["view_id"],
        "view_manifest_sha256": view.get("manifest_sha256") or "",
        "contract_revision": str(view.get("contract_version") or ""),
        "as_of": max(dates) if dates else None,
        "release_ids": release_ids,
        "datasets": datasets,
    }


def request_payload(row: dict) -> dict:
    payload = {
        "factor_name": row["factor_name"],
        "library_name": row["source_library"],
        **PARAMS,
    }
    return payload


def evaluate_result(row: dict, data: dict, snapshot: dict) -> dict:
    fa = data.get("factor_analysis") or {}
    series = fa.get("rank_ic_series")
    evidence = {
        "run_id": data.get("run_id"),
        "report_id": data.get("report_id") or data.get("run_id"),
        "view_id": snapshot["view_id"],
        "view_manifest_sha256": snapshot["view_manifest_sha256"],
        "contract_revision": snapshot["contract_revision"],
        "as_of": snapshot["as_of"],
        "release_ids": snapshot["release_ids"],
        "benchmark": PARAMS,
        "metric_version": (data.get("meta") or {}).get("metric_version") or fa.get("metric_version"),
        "missing": [],
    }
    if not isinstance(series, list) or not series:
        evidence["missing"].append("rank_ic_series")
        return {"status": "pending", "metrics_status": "pending",
                "reason": "R1 日度 Rank IC 未接入，暂不能计算 NW t；已保留回测证据。",
                "metrics": {}, "evidence": evidence}
    try:
        nw = newey_west_t(series)
    except ValueError as exc:
        return {"status": "not_computable", "metrics_status": "not_computable",
                "reason": f"日度 Rank IC 序列不可计算：{exc}", "metrics": {}, "evidence": evidence}
    metrics = data.get("metrics") or {}
    turnover = metrics.get("turnover") or metrics.get("turnover_rate") or fa.get("turnover")
    coverage = fa.get("coverage") if fa.get("coverage") is not None else data.get("coverage")
    rank_ic = fa.get("rank_ic_mean")
    if rank_ic is None:
        rank_ic = metrics.get("rank_ic")
    if not isinstance(turnover, (int, float)) or isinstance(turnover, bool):
        evidence["missing"].append("turnover")
        return {"status": "pending", "metrics_status": "pending",
                "reason": "RE 未返回可核验的长端换手，保留 Rank IC 证据，暂不记 ok。",
                "metrics": {"rank_ic_mean": rank_ic, "newey_west_t": nw["t"],
                            "valid_days": nw["n"], "nw_lags": nw["lags"]},
                "evidence": evidence}
    out = {
        "rank_ic_mean": rank_ic,
        "newey_west_t": nw["t"],
        "valid_days": nw["n"],
        "nw_lags": nw["lags"],
        "turnover": turnover,
        "coverage": coverage,
        "metric_version": evidence["metric_version"],
        "benchmark_version": BENCHMARK_VERSION,
    }
    if coverage is None:
        evidence["missing"].append("coverage")
    return {"status": "ok", "metrics_status": "ok", "reason": "",
            "metrics": out, "evidence": evidence}


def _store(org: int, factor_id: str, result: dict) -> None:
    with get_conn() as c:
        c.execute(
            """UPDATE quant_factor_imported_factors
               SET metrics=%s::jsonb, metrics_status=%s, metrics_reason=%s,
                   metrics_evidence=%s::jsonb, metrics_attempted_at=NOW(), metrics_updated_at=NOW(),
                   updated_at=NOW()
               WHERE org_id=%s AND id=%s""",
            (json.dumps(result.get("metrics") or {}, ensure_ascii=False), result["metrics_status"],
             result["reason"], json.dumps(result["evidence"], ensure_ascii=False), org, factor_id))


def compute_one(org: int, row: dict, snapshot: dict) -> dict:
    status, _, task = proxy_submit_factor_backtest(request_payload(row))
    if status not in (200, 202) or not isinstance(task, dict) or not task.get("run_id"):
        result = {"status": "pending", "metrics_status": "pending",
                  "reason": f"RE 提交失败 HTTP {status}，可重试。", "metrics": {},
                  "evidence": {"view_id": snapshot["view_id"]}}
        _store(org, row["id"], result)
        return result
    rid = task["run_id"]
    deadline = time.monotonic() + _POLL_SECONDS
    while time.monotonic() < deadline:
        status, _, data = proxy_get_factor_run(rid)
        if status == 200 and isinstance(data, dict) and data.get("status") in ("succeeded", "failed", "cancelled"):
            if data.get("status") != "succeeded":
                result = {"status": "not_computable", "metrics_status": "not_computable",
                          "reason": f"RE 计算未成功：{data.get('status')}；{str(data.get('error') or '')[:300]}",
                          "metrics": {}, "evidence": {"run_id": rid, "view_id": snapshot["view_id"]}}
            else:
                result = evaluate_result(row, data, snapshot)
            _store(org, row["id"], result)
            return result
        time.sleep(2)
    result = {"status": "pending", "metrics_status": "pending",
              "reason": "RE 计算超时，可重试；未写入任何指标。", "metrics": {},
              "evidence": {"run_id": rid, "view_id": snapshot["view_id"]}}
    _store(org, row["id"], result)
    return result


def run_batch(org: int, batch_id: str, snapshot: dict) -> None:
    with get_conn() as c:
        rows = [dict(row) for row in c.execute(
            "SELECT * FROM quant_factor_imported_factors WHERE org_id=%s AND batch_id=%s AND metrics_status='pending'",
            (org, batch_id)).fetchall()]
    with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="quant-import-metric") as pool:
        list(pool.map(lambda row: compute_one(org, row, snapshot), rows))


def start_batch(uid: int, org: int, limit: int = 5) -> dict:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("limit 必须是 1—20 的整数")
    snapshot = view_snapshot()
    batch_id = str(uuid.uuid4())
    with get_conn() as c:
        rows = c.execute(
            """SELECT id FROM quant_factor_imported_factors
               WHERE org_id=%s AND status<>'retired' AND metrics_status='pending'
               ORDER BY source_library,source_factor_id LIMIT %s""",
            (org, limit)).fetchall()
        ids = [row["id"] for row in rows]
        if not ids:
            return {"batch_id": batch_id, "queued": 0, "snapshot": snapshot}
        c.execute(
            """UPDATE quant_factor_imported_factors
               SET batch_id=%s, benchmark_version=%s, metrics_params=%s::jsonb,
                   view_id=%s, release_ids=%s::jsonb, view_manifest_sha256=%s,
                   contract_revision=%s, as_of=%s, metrics_status='pending',
                   metrics_reason='队列中：等待后台批次', metrics_attempted_at=NULL, updated_at=NOW()
               WHERE org_id=%s AND id = ANY(%s)""",
            (batch_id, BENCHMARK_VERSION, json.dumps(PARAMS, ensure_ascii=False),
             snapshot["view_id"], json.dumps(snapshot["release_ids"], ensure_ascii=False),
             snapshot["view_manifest_sha256"], snapshot["contract_revision"], snapshot["as_of"],
             org, ids))
    POOL.submit(run_batch, org, batch_id, snapshot)
    return {"batch_id": batch_id, "queued": len(ids), "snapshot": snapshot}


def retry_one(uid: int, org: int, factor_id: str) -> dict:
    snapshot = view_snapshot()
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM quant_factor_imported_factors WHERE org_id=%s AND id=%s",
            (org, factor_id)).fetchone()
        if not row:
            raise KeyError(factor_id)
    return compute_one(org, dict(row), snapshot)


def batch_status(org: int, batch_id: str) -> dict:
    with get_conn() as c:
        rows = c.execute(
            """SELECT metrics_status, COUNT(*) AS n
               FROM quant_factor_imported_factors WHERE org_id=%s AND batch_id=%s
               GROUP BY metrics_status ORDER BY metrics_status""",
            (org, batch_id)).fetchall()
    return {"batch_id": batch_id, "counts": [dict(row) for row in rows]}


__all__ = ["BENCHMARK_VERSION", "PARAMS", "batch_status", "evaluate_result",
           "request_payload", "retry_one", "run_batch", "start_batch", "view_snapshot"]
