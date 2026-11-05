# -*- coding: utf-8 -*-
"""数据平台 view → PG 服务层自动同步。

设计边界：
- 只读数据平台 ``views/current``（或显式 view），不写数据平台；
- 同步 ``md_*`` / ``ref_*`` / ``invest_*`` 服务表，供 Web/H5/机构端读取；
- 以 ``data_sync_state`` 记录已应用的 view；同一 view 默认不重复加载；
- 所有写入在一个事务里，失败回滚，旧数据继续可用。

CLI 见 ``scripts/sync_data_view.py``。定时器/部署见 Batch 2。
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

import pandas as pd
import pyarrow.parquet as pq

from services.core.db import get_conn
from services.core.env_config import env
from services.data import view_loader
from services.invest.schema import ensure_invest_schema, refresh_invest_stocks
from services.marketdata.schema import ensure_marketdata_schema

SYNC_LOCK_KEY = 0x53565144  # "SVQD"
DEFAULT_CONTRACT = "2026-11-01"
DEFAULT_DATA_ROOT = "/home/dev01/project/svquant-data"

BAR_FIELDS = ("open", "high", "low", "close", "volume", "amount", "turnover")
REQUIRED_DATASETS = (
    "daily_bars",
    "daily_bars_unadjusted",
    "valuation_daily",
    "security_status_daily",
    "limit_prices",
    "index_price",
    "security_master",
    "calendar",
    "industry_code_map",
)

STATE_DDL = """
CREATE TABLE IF NOT EXISTS data_sync_state (
  id              SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  view_id         TEXT,
  contract_version TEXT,
  data_date       DATE,
  status          TEXT NOT NULL DEFAULT 'idle',
  last_error      TEXT,
  rows            JSONB,
  started_at      TIMESTAMPTZ,
  finished_at     TIMESTAMPTZ
)
"""

RUN_DDL = """
CREATE TABLE IF NOT EXISTS data_sync_run (
  id          BIGSERIAL PRIMARY KEY,
  view_id     TEXT,
  status      TEXT NOT NULL,
  data_date   DATE,
  rows        JSONB,
  error       TEXT,
  started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ
)
"""


@dataclass(frozen=True)
class ViewInfo:
    view_id: str
    root: Path
    manifest: dict[str, Any]
    contract_version: str
    data_date: date | None

    def dataset(self, name: str) -> dict[str, Any]:
        item = (self.manifest.get("datasets") or {}).get(name)
        if not isinstance(item, dict):
            raise ValueError(f"view {self.view_id} 缺少 dataset: {name}")
        return item

    def dataset_dir(self, name: str) -> Path:
        item = self.dataset(name)
        rel = str(item.get("path") or "").strip()
        if not rel:
            raise ValueError(f"dataset {name} 缺少 path")
        return self.root / rel


def _parse_day(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10] if fmt != "%Y%m%d" else text[:8], fmt).date()
        except ValueError:
            continue
    return None


def _materialized_dir(base: Path) -> Path:
    # `views/current` 通常直接指向某个 view 的 materialized 目录；
    # 显式 view 则是 `views/<id>/materialized`。
    if (base / "manifest.json").exists():
        return base.resolve()
    for name in ("materialized", "materialized-container"):
        candidate = base / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"view 未物化: {base}")


def resolve_view(data_root: str | Path | None = None, view: str = "current") -> ViewInfo:
    root = Path(data_root or env("SVQUANT_DATA_ROOT", DEFAULT_DATA_ROOT) or DEFAULT_DATA_ROOT)
    names = [view]
    if view in {"current", ""}:
        names = ["current"]
    for name in names:
        base = root / "views" / name
        if not base.exists():
            continue
        materialized = _materialized_dir(base)
        manifest_path = materialized / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"缺少 manifest: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        view_id = str(manifest.get("view_id") or "").strip()
        if not view_id:
            raise ValueError(f"manifest 缺少 view_id: {manifest_path}")
        contract = str(manifest.get("contract_version") or "").strip()
        data_date = None
        for key in ("daily_bars", "daily_bars_unadjusted", "valuation_daily"):
            item = (manifest.get("datasets") or {}).get(key) or {}
            data_date = _parse_day(item.get("date_max"))
            if data_date:
                break
        return ViewInfo(view_id, materialized, manifest, contract, data_date)
    raise FileNotFoundError(f"找不到 view: {root / 'views' / view}")


def validate_view(view: ViewInfo, expected_contract: str | None = None) -> None:
    expected = (expected_contract or env("SVQUANT_DATA_CONTRACT", DEFAULT_CONTRACT) or DEFAULT_CONTRACT).strip()
    if view.contract_version != expected:
        raise ValueError(
            f"view {view.view_id} contract={view.contract_version or '-'}，期望 {expected}；拒绝自动同步"
        )
    missing = [name for name in REQUIRED_DATASETS if name not in (view.manifest.get("datasets") or {})]
    if missing:
        raise ValueError(f"view {view.view_id} 缺少 dataset: {', '.join(missing)}")
    if not view.data_date:
        raise ValueError(f"view {view.view_id} 没有 data_date")
    for name in ("daily_bars", "daily_bars_unadjusted", "valuation_daily", "security_status_daily", "limit_prices"):
        item = view.dataset(name)
        dt = _parse_day(item.get("date_max"))
        if dt and dt < view.data_date:
            raise ValueError(f"dataset {name} date_max={dt} < data_date={view.data_date}；拒绝同步")


def _year_of(path: Path) -> int | None:
    match = re.search(r"(?:^|/)year=(\d{4})(?:/|$)", str(path))
    return int(match.group(1)) if match else None


def _dataset_files(
    view: ViewInfo,
    name: str,
    start: date | None = None,
    end: date | None = None,
) -> list[Path]:
    base = view.dataset_dir(name)
    files = sorted(base.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"dataset {name} 没有 parquet: {base}")
    if start or end:
        picked = []
        for path in files:
            year = _year_of(path)
            if year is None:
                picked.append(path)
                continue
            if start and year < start.year:
                continue
            if end and year > end.year:
                continue
            picked.append(path)
        files = picked
    return files


def _iter_frames(
    view: ViewInfo,
    name: str,
    columns: list[str],
    start: date | None = None,
    end: date | None = None,
) -> Iterator[tuple[int | None, pd.DataFrame]]:
    start_s = start.isoformat() if start else None
    end_s = end.isoformat() if end else None
    for path in _dataset_files(view, name, start, end):
        table = pq.read_table(path, columns=columns)
        frame = table.to_pandas()
        if "date" in frame.columns:
            if start_s:
                frame = frame[frame["date"] >= start_s]
            if end_s:
                frame = frame[frame["date"] <= end_s]
        if not frame.empty:
            yield _year_of(path), frame


def _read_frame(
    view: ViewInfo,
    name: str,
    columns: list[str],
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    frames = [frame for _, frame in _iter_frames(view, name, columns, start, end)]
    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _copy_rows(conn, table: str, columns: list[str], rows: Iterable[tuple[Any, ...]]) -> int:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    count = 0
    for row in rows:
        writer.writerow([_clean(value) if value is not None else "" for value in row])
        count += 1
    if not count:
        return 0
    buffer.seek(0)
    with conn.cursor() as cur:
        with cur.copy(
            f"COPY {table} ({','.join(columns)}) FROM STDIN WITH (FORMAT csv, NULL '')"
        ) as copy:
            copy.write(buffer.read())
    return count


def _chunks(values: list[str], size: int) -> Iterator[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def ensure_sync_schema(conn) -> None:
    conn.execute(STATE_DDL)
    conn.execute(RUN_DDL)
    conn.execute(
        "INSERT INTO data_sync_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
    )


def _state(conn) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM data_sync_state WHERE id=1"
    ).fetchone()
    return dict(row) if row else None


def _db_name(conn) -> str:
    row = conn.execute("SELECT current_database() AS db_name").fetchone()
    return str((row or {}).get("db_name") or "")


def _is_safe_db(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered.endswith("_dev")
        or lowered.endswith("_test")
        or "_test" in lowered
        or "_e2e" in lowered
        or lowered.endswith("_local")
    )


def _max_db_date(conn) -> date | None:
    row = conn.execute("SELECT MAX(trade_date) AS d FROM md_daily_bar").fetchone()
    return _parse_day((row or {}).get("d"))


def plan_sync(
    view: ViewInfo,
    state: dict[str, Any] | None,
    *,
    max_db_date: date | None = None,
    full: bool = False,
    force: bool = False,
    from_date: date | None = None,
) -> dict[str, Any]:
    """纯函数：决定本次同步是否执行、从哪天开始。"""
    if not view.data_date:
        raise ValueError("view 没有 data_date")
    if state and state.get("view_id") == view.view_id and not force and not full:
        state_date = _parse_day(state.get("data_date"))
        db_ok = max_db_date is None or state_date is None or max_db_date >= state_date
        if state_date and state_date >= view.data_date and db_ok:
            return {
                "status": "unchanged",
                "view_id": view.view_id,
                "data_date": view.data_date.isoformat(),
                "start": None,
                "end": view.data_date.isoformat(),
            }
    if full:
        start = date(2016, 1, 1)
    elif from_date:
        start = from_date
    else:
        candidates = [d for d in (_parse_day((state or {}).get("data_date")), max_db_date) if d]
        start = (min(candidates) + timedelta(days=1)) if candidates else date(2016, 1, 1)
    end = view.data_date
    if start > end and not force and not full:
        # 新 view 可能数据日不变、只补了行业/指数权重/risk_daily 等派生列；
        # 这种情况仍要跑一次轻量元数据同步，不能直接 fresh。
        if state and state.get("view_id") and state.get("view_id") != view.view_id:
            return {
                "status": "sync_meta",
                "view_id": view.view_id,
                "data_date": end.isoformat(),
                "start": end.isoformat(),
                "end": end.isoformat(),
            }
        return {
            "status": "fresh",
            "view_id": view.view_id,
            "data_date": end.isoformat(),
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
    return {
        "status": "sync",
        "view_id": view.view_id,
        "data_date": end.isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


def _upsert_state(conn, view: ViewInfo, status: str, rows: dict[str, int] | None = None, error: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO data_sync_state
          (id, view_id, contract_version, data_date, status, last_error, rows, started_at, finished_at)
        VALUES (1, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (id) DO UPDATE SET
          view_id=EXCLUDED.view_id,
          contract_version=EXCLUDED.contract_version,
          data_date=EXCLUDED.data_date,
          status=EXCLUDED.status,
          last_error=EXCLUDED.last_error,
          rows=EXCLUDED.rows,
          finished_at=NOW()
        """,
        (
            view.view_id,
            view.contract_version,
            view.data_date,
            status,
            error,
            json.dumps(rows or {}, ensure_ascii=False),
        ),
    )


def _record_run(conn, view: ViewInfo, status: str, rows: dict[str, int] | None = None, error: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO data_sync_run (view_id, status, data_date, rows, error, finished_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        """,
        (
            view.view_id,
            status,
            view.data_date,
            json.dumps(rows or {}, ensure_ascii=False),
            error,
        ),
    )


def _record_failure(view: ViewInfo | None, error: str) -> None:
    try:
        with get_conn() as conn:
            ensure_sync_schema(conn)
            if view:
                _upsert_state(conn, view, "failed", error=error[:2000])
                _record_run(conn, view, "failed", error=error[:2000])
    except Exception:
        # 失败日志不能覆盖原始异常
        pass


def _last_closes(conn, symbols: list[str], before: date) -> dict[str, float]:
    if not symbols:
        return {}
    rows = conn.execute(
        """
        SELECT DISTINCT ON (symbol) symbol, close
          FROM md_daily_bar
         WHERE adjust='hfq' AND trade_date < %s AND symbol = ANY(%s)
         ORDER BY symbol, trade_date DESC
        """,
        (before, symbols),
    ).fetchall()
    return {str(r["symbol"]): float(r["close"]) for r in rows if r.get("close") is not None}


def _hfq_columns(view: ViewInfo) -> tuple[Path, dict[str, set[str]]]:
    files = _dataset_files(view, "daily_bars")
    path = files[0]
    names = pq.ParquetFile(path).schema_arrow.names
    symbols: dict[str, set[str]] = {}
    for name in names:
        match = re.match(r"\('([^']+)', '([^']+)'\)", name)
        if match:
            symbols.setdefault(match.group(1), set()).add(match.group(2))
    return path, symbols


def _sync_hfq_bars(conn, view: ViewInfo, start: date, end: date) -> int:
    path, symbol_fields = _hfq_columns(view)
    symbols = sorted(symbol_fields)
    last = _last_closes(conn, symbols, start)
    total = 0
    for batch in _chunks(symbols, 400):
        fields = [f for f in BAR_FIELDS if any(f in symbol_fields[s] for s in batch)]
        columns = ["date"]
        key_map: dict[str, tuple[str, str]] = {}
        for symbol in batch:
            for field in fields:
                if field not in symbol_fields[symbol]:
                    continue
                name = f"('{symbol}', '{field}')"
                columns.append(name)
                key_map[name] = (symbol, field)
        if len(columns) == 1:
            continue
        table = pq.read_table(path, columns=columns).to_pandas()
        # pandas 会把 (symbol, field) 列名解析成 MultiIndex，date 变成索引；
        # 统一还原成 'date' + "('symbol', 'field')"，与 key_map 对齐。
        table = table.reset_index()
        table.columns = [
            str(col[0]) if isinstance(col, tuple) and (len(col) < 2 or not col[1])
            else (f"('{col[0]}', '{col[1]}')" if isinstance(col, tuple) else str(col))
            for col in table.columns
        ]
        table = table[(table["date"] >= start.isoformat()) & (table["date"] <= end.isoformat())]
        if table.empty:
            continue
        long = table.melt(id_vars="date", var_name="key", value_name="value")
        long["symbol"] = long["key"].map(lambda k: key_map[k][0])
        long["field"] = long["key"].map(lambda k: key_map[k][1])
        pivot = (
            long.pivot_table(index=["symbol", "date"], columns="field", values="value", aggfunc="first")
            .reset_index()
            .sort_values(["symbol", "date"])
        )
        for field in BAR_FIELDS:
            if field not in pivot.columns:
                pivot[field] = None
        pivot["pre_close"] = pivot.groupby("symbol")["close"].shift()
        first = pivot.groupby("symbol", sort=False).head(1)
        for _, row in first.iterrows():
            prev = last.get(str(row["symbol"]))
            if prev is not None:
                pivot.loc[row.name, "pre_close"] = prev
        rows = (
            (
                str(row.symbol),
                str(row.date)[:10],
                _clean(row.open),
                _clean(row.high),
                _clean(row.low),
                _clean(row.close),
                _clean(row.pre_close),
                _clean(row.volume),
                _clean(row.amount),
                _clean(row.turnover),
                "hfq",
                view.view_id,
            )
            for row in pivot.itertuples(index=False)
        )
        total += _copy_rows(
            conn,
            "tmp_md_daily_bar",
            ["symbol", "trade_date", "open", "high", "low", "close", "pre_close",
             "volume", "amount", "turnover", "adjust", "source"],
            rows,
        )
    return total


def _sync_unadjusted_bars(conn, view: ViewInfo, start: date, end: date) -> int:
    total = 0
    # 用 limit_prices 的 pre_close 补未复权前收；缺失时按 symbol 前移。
    all_limits = _read_frame(view, "limit_prices", ["date", "symbol", "pre_close"], start, end)
    for _, frame in _iter_frames(
        view,
        "daily_bars_unadjusted",
        ["date", "symbol", "open", "high", "low", "close", "volume", "amount", "turnover"],
        start,
        end,
    ):
        limits = all_limits[all_limits["date"].isin(frame["date"].unique())]
        if not limits.empty:
            frame = frame.merge(limits, on=["date", "symbol"], how="left")
        else:
            frame["pre_close"] = None
        frame = frame.sort_values(["symbol", "date"])
        shift = frame.groupby("symbol")["close"].shift()
        frame["pre_close"] = frame["pre_close"].where(frame["pre_close"].notna(), shift)
        rows = (
            (
                str(row.symbol),
                str(row.date)[:10],
                _clean(row.open),
                _clean(row.high),
                _clean(row.low),
                _clean(row.close),
                _clean(row.pre_close),
                _clean(row.volume),
                _clean(row.amount),
                _clean(row.turnover),
                "none",
                view.view_id,
            )
            for row in frame.itertuples(index=False)
        )
        total += _copy_rows(
            conn,
            "tmp_md_daily_bar",
            ["symbol", "trade_date", "open", "high", "low", "close", "pre_close",
             "volume", "amount", "turnover", "adjust", "source"],
            rows,
        )
    return total


def _sync_valuations(conn, view: ViewInfo, start: date, end: date) -> int:
    frame = view_loader.valuation_frame(
        start.isoformat(), end.isoformat(), root=view.root
    )
    if frame.empty:
        return 0
    columns = [
        "symbol", "date", "pe_ttm", "pb_mrq", "pcf_ocf_ttm",
        "dividend_yield_ttm", "float_mv", "total_mv", "source",
    ]
    rows = (
        (
            str(row.symbol),
            str(row.date)[:10],
            _clean(row.pe_ttm),
            _clean(row.pb_mrq),
            _clean(row.pcf_ocf_ttm),
            _clean(row.dividend_yield_ttm),
            _clean(row.float_mv),
            _clean(row.total_mv),
            str(row.source or view.view_id),
        )
        for row in frame[columns].itertuples(index=False)
    )
    return _copy_rows(
        conn,
        "tmp_md_valuation_daily",
        ["symbol", "trade_date", "pe_ttm", "pb_mrq", "pcf_ocf_ttm",
         "dividend_yield_ttm", "float_mv", "total_mv", "source"],
        rows,
    )


def _sync_status(conn, view: ViewInfo, start: date, end: date) -> int:
    total = 0
    all_limits = _read_frame(
        view, "limit_prices", ["date", "symbol", "upper_limit", "lower_limit"], start, end
    )
    for _, status in _iter_frames(
        view,
        "security_status_daily",
        ["date", "symbol", "listed_status", "up_and_down_status", "is_st", "is_suspended"],
        start,
        end,
    ):
        limits = all_limits[all_limits["date"].isin(status["date"].unique())]
        if not limits.empty:
            status = status.merge(limits, on=["date", "symbol"], how="left")
        else:
            status["upper_limit"] = None
            status["lower_limit"] = None
        rows = (
            (
                str(row.symbol),
                str(row.date)[:10],
                _clean(row.listed_status),
                _clean(row.up_and_down_status),
                _clean(row.is_st),
                _clean(row.is_suspended),
                _clean(row.upper_limit),
                _clean(row.lower_limit),
                view.view_id,
            )
            for row in status.itertuples(index=False)
        )
        total += _copy_rows(
            conn,
            "tmp_md_status_daily",
            ["symbol", "trade_date", "listed_status", "up_down_status", "is_st",
             "is_suspended", "limit_up", "limit_down", "source"],
            rows,
        )
    return total


def _index_frames(view: ViewInfo):
    """兼容旧 view：新 view 的 index_price 才有 volume/amount。"""
    base = ["date", "index_code", "open", "high", "low", "close"]
    try:
        yield from _iter_frames(view, "index_price", base + ["volume", "amount"])
    except Exception:
        yield from _iter_frames(view, "index_price", base)


def _sync_index(conn, view: ViewInfo) -> int:
    total = 0
    for _, frame in _index_frames(view):
        has_volume = "volume" in frame.columns
        has_amount = "amount" in frame.columns
        rows = []
        for row in frame.itertuples(index=False):
            rows.append((
                str(row.index_code),
                str(row.date)[:10],
                _clean(row.open),
                _clean(row.high),
                _clean(row.low),
                _clean(row.close),
                _clean(getattr(row, "volume", None)) if has_volume else None,
                _clean(getattr(row, "amount", None)) if has_amount else None,
                view.view_id,
            ))
        total += _copy_rows(
            conn,
            "tmp_md_index_bar",
            ["index_code", "trade_date", "open", "high", "low", "close",
             "volume", "amount", "source"],
            rows,
        )
    return total


_FUND_FLOW_DAILY_COLUMNS = [
    "date", "symbol", "main_net_inflow", "small_net_inflow", "medium_net_inflow",
    "large_net_inflow", "super_large_net_inflow", "main_net_ratio", "small_net_ratio",
    "medium_net_ratio", "large_net_ratio", "super_large_net_ratio", "close",
    "change_pct", "source", "observed_at",
]
_FUND_FLOW_CANDIDATE_COLUMNS = [
    "symbol", "trade_date", "main_net_inflow_5d", "main_net_inflow_latest",
    "main_net_ratio_latest", "inflow_days_5d", "consecutive_inflow_days",
    "consecutive_outflow_days", "days_available", "source", "observed_at",
]


def _sync_fund_flow_daily(conn, view: ViewInfo) -> int:
    if "fund_flow_daily" not in (view.manifest.get("datasets") or {}):
        return 0
    total = 0
    for _, frame in _iter_frames(view, "fund_flow_daily", _FUND_FLOW_DAILY_COLUMNS):
        rows = (
            (
                str(row.symbol), str(row.date)[:10], _clean(row.main_net_inflow),
                _clean(row.small_net_inflow), _clean(row.medium_net_inflow),
                _clean(row.large_net_inflow), _clean(row.super_large_net_inflow),
                _clean(row.main_net_ratio), _clean(row.small_net_ratio),
                _clean(row.medium_net_ratio), _clean(row.large_net_ratio),
                _clean(row.super_large_net_ratio), _clean(row.close),
                _clean(row.change_pct), _clean(row.source), _clean(row.observed_at),
            )
            for row in frame.itertuples(index=False)
        )
        total += _copy_rows(conn, "tmp_md_fund_flow_daily", [
            "symbol", "trade_date", "main_net_inflow", "small_net_inflow",
            "medium_net_inflow", "large_net_inflow", "super_large_net_inflow",
            "main_net_ratio", "small_net_ratio", "medium_net_ratio",
            "large_net_ratio", "super_large_net_ratio", "close", "change_pct",
            "source", "observed_at",
        ], rows)
    return total


def _sync_fund_flow_candidate(conn, view: ViewInfo) -> int:
    if "fund_flow_candidate" not in (view.manifest.get("datasets") or {}):
        return 0
    total = 0
    for _, frame in _iter_frames(view, "fund_flow_candidate", _FUND_FLOW_CANDIDATE_COLUMNS):
        rows = (
            (
                str(row.symbol), str(row.trade_date)[:10], _clean(row.main_net_inflow_5d),
                _clean(row.main_net_inflow_latest), _clean(row.main_net_ratio_latest),
                _clean(row.inflow_days_5d), _clean(row.consecutive_inflow_days),
                _clean(row.consecutive_outflow_days), _clean(row.days_available),
                _clean(row.source), _clean(row.observed_at),
            )
            for row in frame.itertuples(index=False)
        )
        total += _copy_rows(conn, "tmp_md_fund_flow_candidate", _FUND_FLOW_CANDIDATE_COLUMNS, rows)
    return total


def _sync_risk(conn, view: ViewInfo, start: date, end: date) -> int:
    """可选：数据平台提供 risk_daily 时同步到 md_risk_daily。"""
    if "risk_daily" not in (view.manifest.get("datasets") or {}):
        return 0
    total = 0
    for _, frame in _iter_frames(
        view,
        "risk_daily",
        ["date", "symbol", "beta_1y", "vol_1y", "max_drawdown_1y", "calc_version"],
        start,
        end,
    ):
        rows = (
            (
                str(row.symbol),
                str(row.date)[:10],
                _clean(row.beta_1y),
                _clean(row.vol_1y),
                _clean(row.max_drawdown_1y),
                str(row.calc_version or "v1"),
            )
            for row in frame.itertuples(index=False)
        )
        total += _copy_rows(
            conn,
            "tmp_md_risk_daily",
            ["symbol", "trade_date", "beta_1y", "vol_1y", "max_drawdown_1y", "calc_version"],
            rows,
        )
    return total


def _sync_us_stock(conn, view: ViewInfo) -> int:
    """可选：数据平台 us_stock_snapshot → md_us_stock_snapshot。"""
    if "us_stock_snapshot" not in (view.manifest.get("datasets") or {}):
        return 0
    total = 0
    for _, frame in _iter_frames(
        view,
        "us_stock_snapshot",
        ["symbol", "name", "last", "prev_close", "amount", "turnover", "trade_date", "market"],
    ):
        rows = (
            (
                str(row.symbol),
                str(row.name or "") or None,
                _clean(row.last),
                _clean(row.prev_close),
                _clean(row.amount),
                _clean(row.turnover),
                str(row.trade_date)[:10] if row.trade_date else None,
                str(row.market or "US"),
                view.view_id,
            )
            for row in frame.itertuples(index=False)
        )
        total += _copy_rows(
            conn,
            "tmp_md_us_stock_snapshot",
            ["symbol", "name", "last", "prev_close", "amount", "turnover",
             "trade_date", "market", "source"],
            rows,
        )
    return total


def _sync_ref_security(conn, view: ViewInfo) -> int:
    files = _dataset_files(view, "security_master")
    frame = pq.read_table(
        files[0], columns=["Symbol", "Name", "IsQuitGP", "J_start", "HSStockKind"]
    ).to_pandas()
    # 1=沪深主板、2=北交所、3=创业板、4=科创板；只同步股票，不把基金/指数混进来。
    frame = frame[frame["HSStockKind"].astype(str).isin({"1", "2", "3", "4"})]
    rows = []
    for row in frame.itertuples(index=False):
        symbol = str(row.Symbol or "").strip()
        if not symbol or "." not in symbol:
            continue
        code, _, exchange = symbol.partition(".")
        if code.startswith(("688", "689")):
            board = "STAR"
        elif code.startswith(("300", "301")):
            board = "ChiNext"
        elif code.startswith(("8", "4", "92")):
            board = "BSE"
        elif exchange == "SH":
            board = "SH_MAIN"
        elif exchange == "SZ":
            board = "SZ_MAIN"
        else:
            board = "OTHER"
        raw_start = str(row.J_start or "").strip()
        list_date = _parse_day(raw_start)
        status = "delisted" if str(row.IsQuitGP or "").strip() == "1" else "listed"
        rows.append((symbol, str(row.Name or "") or None, "CN", exchange, board,
                     list_date.isoformat() if list_date else None, status, view.view_id))
    return _copy_rows(
        conn,
        "tmp_ref_security",
        ["symbol", "name", "market", "exchange", "board", "list_date", "status", "source"],
        rows,
    )


def _sync_calendar(conn, view: ViewInfo) -> int:
    files = _dataset_files(view, "calendar")
    frame = pq.read_table(files[0], columns=["TradingDate", "IsTradingDay"]).to_pandas()
    rows = []
    for row in frame.itertuples(index=False):
        day = _parse_day(row.TradingDate)
        if not day:
            continue
        rows.append(("CN", day.isoformat(), "true" if int(row.IsTradingDay or 0) else "false", view.view_id))
    return _copy_rows(
        conn, "tmp_ref_trading_calendar", ["market", "trade_date", "is_open", "source"], rows
    )


def _sync_industry(conn, view: ViewInfo) -> int:
    files = _dataset_files(view, "industry_code_map")
    frame = pq.read_table(
        files[0], columns=["symbol", "sw_l1_code", "sw_l1_name", "as_of"]
    ).to_pandas()
    industries: dict[str, str] = {}
    rows = []
    for row in frame.itertuples(index=False):
        symbol = str(row.symbol or "").strip()
        code = str(row.sw_l1_code or "").strip()
        if not symbol or not code:
            continue
        name = str(row.sw_l1_name or "").strip() or None
        industries[code] = name or ""
        day = _parse_day(row.as_of) or view.data_date
        rows.append((symbol, code, 1, (day or date.today()).isoformat(), view.view_id))
    count = _copy_rows(
        conn,
        "tmp_ref_security_industry",
        ["symbol", "industry_code", "level", "effective_from", "source"],
        rows,
    )
    if industries:
        _copy_rows(
            conn,
            "tmp_ref_industry",
            ["industry_code", "level", "name", "source"],
            ((code, 1, name or None, view.view_id) for code, name in industries.items()),
        )
    return count


def _refresh_serving(conn, view: ViewInfo) -> int:
    count = refresh_invest_stocks(conn)
    conn.execute(
        """
        INSERT INTO invest_meta (key, value) VALUES
          ('dataDate', %s), ('dataView', %s), ('dataSyncedAt', %s)
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
        """,
        (view.data_date.isoformat(), view.view_id, datetime.now().isoformat(timespec="seconds")),
    )
    return int(count)


def _sync_news_dataset(conn, view: ViewInfo) -> int:
    """可选：数据平台 news 数据集，供 H5 资讯页读取；与 doc_item 去重。"""
    if "news" not in (view.manifest.get("datasets") or {}):
        return 0
    frame = _read_frame(
        view, "news", ["doc_id", "source", "published_at", "title", "url", "symbol", "summary"]
    )
    if frame.empty:
        return 0
    conn.execute("DELETE FROM derived_news")
    rows = []
    for row in frame.itertuples(index=False):
        doc_id = str(row.doc_id or "").strip()
        if not doc_id:
            continue
        published = row.published_at
        published_text = None
        try:
            if published is not None and not pd.isna(published):
                published_text = str(published)[:19]
        except (TypeError, ValueError):
            published_text = None
        rows.append(
            (
                doc_id,
                _clean(row.source),
                published_text,
                str(row.title or ""),
                _clean(row.url),
                _clean(row.symbol),
                _clean(row.summary),
                view.data_date,
            )
        )
    return _copy_rows(
        conn,
        "derived_news",
        ["doc_id", "source", "published_at", "title", "url", "symbol", "summary", "as_of"],
        rows,
    )


def _prepare_temp_tables(conn) -> None:
    ddl = (
        "CREATE TEMP TABLE IF NOT EXISTS tmp_md_daily_bar (LIKE md_daily_bar INCLUDING DEFAULTS) ON COMMIT DROP",
        "CREATE TEMP TABLE IF NOT EXISTS tmp_md_valuation_daily (LIKE md_valuation_daily INCLUDING DEFAULTS) ON COMMIT DROP",
        "CREATE TEMP TABLE IF NOT EXISTS tmp_md_status_daily (LIKE md_status_daily INCLUDING DEFAULTS) ON COMMIT DROP",
        "CREATE TEMP TABLE IF NOT EXISTS tmp_md_index_bar (LIKE md_index_bar INCLUDING DEFAULTS) ON COMMIT DROP",
        "CREATE TEMP TABLE IF NOT EXISTS tmp_md_risk_daily (LIKE md_risk_daily INCLUDING DEFAULTS) ON COMMIT DROP",
        "CREATE TEMP TABLE IF NOT EXISTS tmp_md_fund_flow_daily (LIKE md_fund_flow_daily INCLUDING DEFAULTS) ON COMMIT DROP",
        "CREATE TEMP TABLE IF NOT EXISTS tmp_md_fund_flow_candidate (LIKE md_fund_flow_candidate INCLUDING DEFAULTS) ON COMMIT DROP",
        "CREATE TEMP TABLE IF NOT EXISTS tmp_md_us_stock_snapshot (LIKE md_us_stock_snapshot INCLUDING DEFAULTS) ON COMMIT DROP",
        "CREATE TEMP TABLE IF NOT EXISTS tmp_ref_security (LIKE ref_security INCLUDING DEFAULTS) ON COMMIT DROP",
        "CREATE TEMP TABLE IF NOT EXISTS tmp_ref_trading_calendar (LIKE ref_trading_calendar INCLUDING DEFAULTS) ON COMMIT DROP",
        "CREATE TEMP TABLE IF NOT EXISTS tmp_ref_security_industry (LIKE ref_security_industry INCLUDING DEFAULTS) ON COMMIT DROP",
        "CREATE TEMP TABLE IF NOT EXISTS tmp_ref_industry (LIKE ref_industry INCLUDING DEFAULTS) ON COMMIT DROP",
    )
    for statement in ddl:
        conn.execute(statement)


def _prune_us_snapshot(conn) -> int:
    """美股快照是 active set：删除更名/退市旧代码，避免 invest_stocks 残留。"""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM tmp_md_us_stock_snapshot"
    ).fetchone()
    count = int((row or {}).get("n") or 0)
    if count <= 0:
        return 0
    conn.execute(
        """
        DELETE FROM md_us_stock_snapshot m
         WHERE NOT EXISTS (
           SELECT 1 FROM tmp_md_us_stock_snapshot t WHERE t.symbol = m.symbol
         )
        """
    )
    return count


def _merge_temp_tables(conn) -> None:
    conn.execute(
        """
        INSERT INTO md_daily_bar
          (symbol, trade_date, open, high, low, close, pre_close, volume, amount, turnover, adjust, source, ingested_at)
        SELECT symbol, trade_date, open, high, low, close, pre_close, volume, amount, turnover, adjust, source, NOW()
          FROM tmp_md_daily_bar
        ON CONFLICT (symbol, trade_date, adjust) DO UPDATE SET
          open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close,
          pre_close=COALESCE(EXCLUDED.pre_close, md_daily_bar.pre_close),
          volume=EXCLUDED.volume, amount=EXCLUDED.amount, turnover=EXCLUDED.turnover,
          source=EXCLUDED.source, ingested_at=NOW()
        """
    )
    conn.execute(
        """
        INSERT INTO md_valuation_daily
          (symbol, trade_date, pe_ttm, pb_mrq, pcf_ocf_ttm, dividend_yield_ttm,
           float_mv, total_mv, source, ingested_at)
        SELECT symbol, trade_date, pe_ttm, pb_mrq, pcf_ocf_ttm, dividend_yield_ttm,
               float_mv, total_mv, source, NOW()
          FROM tmp_md_valuation_daily
        ON CONFLICT (symbol, trade_date) DO UPDATE SET
          pe_ttm=EXCLUDED.pe_ttm, pb_mrq=EXCLUDED.pb_mrq,
          pcf_ocf_ttm=EXCLUDED.pcf_ocf_ttm,
          dividend_yield_ttm=EXCLUDED.dividend_yield_ttm,
          float_mv=EXCLUDED.float_mv, total_mv=EXCLUDED.total_mv,
          source=EXCLUDED.source, ingested_at=NOW()
        """
    )
    conn.execute(
        """
        INSERT INTO md_status_daily
          (symbol, trade_date, listed_status, up_down_status, is_st, is_suspended, limit_up, limit_down, source)
        SELECT symbol, trade_date, listed_status, up_down_status, is_st, is_suspended, limit_up, limit_down, source
          FROM tmp_md_status_daily
        ON CONFLICT (symbol, trade_date) DO UPDATE SET
          listed_status=EXCLUDED.listed_status,
          up_down_status=EXCLUDED.up_down_status,
          is_st=COALESCE(EXCLUDED.is_st, md_status_daily.is_st),
          is_suspended=COALESCE(EXCLUDED.is_suspended, md_status_daily.is_suspended),
          limit_up=COALESCE(EXCLUDED.limit_up, md_status_daily.limit_up),
          limit_down=COALESCE(EXCLUDED.limit_down, md_status_daily.limit_down),
          source=EXCLUDED.source
        """
    )
    conn.execute(
        """
        INSERT INTO md_index_bar (index_code, trade_date, open, high, low, close, volume, amount, source)
        SELECT index_code, trade_date, open, high, low, close, volume, amount, source FROM tmp_md_index_bar
        ON CONFLICT (index_code, trade_date) DO UPDATE SET
          open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close,
          volume=COALESCE(EXCLUDED.volume, md_index_bar.volume),
          amount=COALESCE(EXCLUDED.amount, md_index_bar.amount),
          source=EXCLUDED.source
        """
    )
    conn.execute(
        """
        INSERT INTO md_risk_daily
          (symbol, trade_date, beta_1y, vol_1y, max_drawdown_1y, calc_version)
        SELECT symbol, trade_date, beta_1y, vol_1y, max_drawdown_1y, calc_version
          FROM tmp_md_risk_daily
        ON CONFLICT (symbol, trade_date, calc_version) DO UPDATE SET
          beta_1y=EXCLUDED.beta_1y, vol_1y=EXCLUDED.vol_1y,
          max_drawdown_1y=EXCLUDED.max_drawdown_1y
        """
    )
    conn.execute(
        """
        INSERT INTO md_fund_flow_daily
          (symbol, trade_date, main_net_inflow, small_net_inflow, medium_net_inflow,
           large_net_inflow, super_large_net_inflow, main_net_ratio, small_net_ratio,
           medium_net_ratio, large_net_ratio, super_large_net_ratio, close, change_pct,
           source, observed_at, ingested_at)
        SELECT symbol, trade_date, main_net_inflow, small_net_inflow, medium_net_inflow,
               large_net_inflow, super_large_net_inflow, main_net_ratio, small_net_ratio,
               medium_net_ratio, large_net_ratio, super_large_net_ratio, close, change_pct,
               source, observed_at, NOW()
          FROM tmp_md_fund_flow_daily
        ON CONFLICT (symbol, trade_date) DO UPDATE SET
          main_net_inflow=EXCLUDED.main_net_inflow,
          small_net_inflow=EXCLUDED.small_net_inflow,
          medium_net_inflow=EXCLUDED.medium_net_inflow,
          large_net_inflow=EXCLUDED.large_net_inflow,
          super_large_net_inflow=EXCLUDED.super_large_net_inflow,
          main_net_ratio=EXCLUDED.main_net_ratio,
          small_net_ratio=EXCLUDED.small_net_ratio,
          medium_net_ratio=EXCLUDED.medium_net_ratio,
          large_net_ratio=EXCLUDED.large_net_ratio,
          super_large_net_ratio=EXCLUDED.super_large_net_ratio,
          close=EXCLUDED.close, change_pct=EXCLUDED.change_pct,
          source=EXCLUDED.source, observed_at=EXCLUDED.observed_at, ingested_at=NOW()
        """
    )
    conn.execute(
        """
        INSERT INTO md_fund_flow_candidate
          (symbol, trade_date, main_net_inflow_5d, main_net_inflow_latest,
           main_net_ratio_latest, inflow_days_5d, consecutive_inflow_days,
           consecutive_outflow_days, days_available, source, observed_at, ingested_at)
        SELECT symbol, trade_date, main_net_inflow_5d, main_net_inflow_latest,
               main_net_ratio_latest, inflow_days_5d, consecutive_inflow_days,
               consecutive_outflow_days, days_available, source, observed_at, NOW()
          FROM tmp_md_fund_flow_candidate
        ON CONFLICT (symbol) DO UPDATE SET
          trade_date=EXCLUDED.trade_date,
          main_net_inflow_5d=EXCLUDED.main_net_inflow_5d,
          main_net_inflow_latest=EXCLUDED.main_net_inflow_latest,
          main_net_ratio_latest=EXCLUDED.main_net_ratio_latest,
          inflow_days_5d=EXCLUDED.inflow_days_5d,
          consecutive_inflow_days=EXCLUDED.consecutive_inflow_days,
          consecutive_outflow_days=EXCLUDED.consecutive_outflow_days,
          days_available=EXCLUDED.days_available,
          source=EXCLUDED.source, observed_at=EXCLUDED.observed_at, ingested_at=NOW()
        """
    )
    _prune_us_snapshot(conn)
    conn.execute(
        """
        INSERT INTO md_us_stock_snapshot
          (symbol, name, last, prev_close, amount, turnover, trade_date, market, source, ingested_at)
        SELECT symbol, name, last, prev_close, amount, turnover, trade_date, market, source, NOW()
          FROM tmp_md_us_stock_snapshot
        ON CONFLICT (symbol) DO UPDATE SET
          name=EXCLUDED.name, last=EXCLUDED.last, prev_close=EXCLUDED.prev_close,
          amount=EXCLUDED.amount, turnover=EXCLUDED.turnover,
          trade_date=EXCLUDED.trade_date, market=EXCLUDED.market,
          source=EXCLUDED.source, ingested_at=NOW()
        """
    )
    conn.execute(
        """
        INSERT INTO ref_security (symbol, name, market, exchange, board, list_date, status, source, updated_at)
        SELECT symbol, name, market, exchange, board, list_date, status, source, NOW()
          FROM tmp_ref_security
        ON CONFLICT (symbol) DO UPDATE SET
          name=COALESCE(EXCLUDED.name, ref_security.name),
          market=EXCLUDED.market,
          exchange=EXCLUDED.exchange,
          board=EXCLUDED.board,
          list_date=COALESCE(ref_security.list_date, EXCLUDED.list_date),
          status=EXCLUDED.status,
          source=EXCLUDED.source,
          updated_at=NOW()
        """
    )
    conn.execute(
        """
        INSERT INTO ref_trading_calendar (market, trade_date, is_open, source)
        SELECT market, trade_date, is_open, source FROM tmp_ref_trading_calendar
        ON CONFLICT (market, trade_date) DO UPDATE SET
          is_open=EXCLUDED.is_open, source=EXCLUDED.source
        """
    )
    conn.execute(
        """
        INSERT INTO ref_security_industry
          (symbol, industry_code, level, effective_from, source)
        SELECT symbol, industry_code, level, effective_from, source FROM tmp_ref_security_industry
        ON CONFLICT (symbol, industry_code, level, effective_from) DO UPDATE SET
          source=EXCLUDED.source
        """
    )
    conn.execute(
        """
        INSERT INTO ref_industry (industry_code, level, name, source)
        SELECT industry_code, level, name, source FROM tmp_ref_industry
        ON CONFLICT (industry_code, level) DO UPDATE SET
          name=COALESCE(EXCLUDED.name, ref_industry.name),
          source=EXCLUDED.source
        """
    )


def sync_view(
    view_name: str = "current",
    *,
    data_root: str | Path | None = None,
    dry_run: bool = False,
    full: bool = False,
    force: bool = False,
    from_date: date | None = None,
    with_financials: bool = False,
    allow_production: bool = False,
) -> dict[str, Any]:
    view = resolve_view(data_root, view_name)
    validate_view(view)

    if not dry_run:
        with get_conn() as conn:
            db_name = _db_name(conn)
        if not _is_safe_db(db_name) and not allow_production:
            raise PermissionError(
                f"拒绝写入数据库 {db_name}：只允许 *_dev/*_test/*_e2e；"
                "生产库必须显式 --allow-production"
            )

    if dry_run:
        state = None
        try:
            with get_conn() as conn:
                exists = conn.execute("SELECT to_regclass('public.data_sync_state') AS t").fetchone()
                if exists and exists.get("t"):
                    state = _state(conn)
                max_db = _max_db_date(conn)
        except Exception:
            max_db = None
        plan = plan_sync(view, state, max_db_date=max_db, full=full, force=force, from_date=from_date)
        return {**plan, "dryRun": True, "contract": view.contract_version, "root": str(view.root)}

    ensure_marketdata_schema()
    ensure_invest_schema()
    with get_conn() as conn:
        ensure_sync_schema(conn)
        got = conn.execute("SELECT pg_try_advisory_lock(%s) AS ok", (SYNC_LOCK_KEY,)).fetchone()
        if not got or not got.get("ok"):
            return {"status": "locked", "view_id": view.view_id}
        try:
            state = _state(conn)
            plan = plan_sync(
                view, state, max_db_date=_max_db_date(conn), full=full, force=force, from_date=from_date
            )
            if plan["status"] in {"unchanged", "fresh"}:
                _upsert_state(conn, view, "ok", rows=(state or {}).get("rows"))
                return plan
            if plan["status"] == "sync_meta":
                end = _parse_day(plan["end"])
                assert end
                _prepare_temp_tables(conn)
                rows: dict[str, int] = {}
                rows["ref_security"] = _sync_ref_security(conn, view)
                rows["calendar"] = _sync_calendar(conn, view)
                rows["industry"] = _sync_industry(conn, view)
                rows["index"] = _sync_index(conn, view)
                rows["risk"] = _sync_risk(conn, view, end, end)
                rows["us_stock"] = _sync_us_stock(conn, view)
                rows["news"] = _sync_news_dataset(conn, view)
                _merge_temp_tables(conn)
                rows["invest_stocks"] = _refresh_serving(conn, view)
                _upsert_state(conn, view, "ok", rows=rows)
                _record_run(conn, view, "ok", rows=rows)
                return {**plan, "status": "ok", "rows": rows}
            start = _parse_day(plan["start"])
            end = _parse_day(plan["end"])
            assert start and end
            _prepare_temp_tables(conn)
            rows: dict[str, int] = {}
            rows["ref_security"] = _sync_ref_security(conn, view)
            rows["calendar"] = _sync_calendar(conn, view)
            rows["industry"] = _sync_industry(conn, view)
            rows["bars_hfq"] = _sync_hfq_bars(conn, view, start, end)
            rows["bars_none"] = _sync_unadjusted_bars(conn, view, start, end)
            rows["valuations"] = _sync_valuations(conn, view, start, end)
            rows["status"] = _sync_status(conn, view, start, end)
            rows["index"] = _sync_index(conn, view)
            rows["risk"] = _sync_risk(conn, view, start, end)
            rows["fund_flow_daily"] = _sync_fund_flow_daily(conn, view)
            rows["fund_flow_candidate"] = _sync_fund_flow_candidate(conn, view)
            rows["us_stock"] = _sync_us_stock(conn, view)
            rows["news"] = _sync_news_dataset(conn, view)
            if with_financials:
                financial = view_loader.load_financials(root=view.root)
                rows["financials"] = sum(int(v or 0) for v in financial.values())
            _merge_temp_tables(conn)
            rows["invest_stocks"] = _refresh_serving(conn, view)
            _upsert_state(conn, view, "ok", rows=rows)
            _record_run(conn, view, "ok", rows=rows)
            return {**plan, "status": "ok", "rows": rows}
        except Exception as exc:
            # 先回滚释放锁，再用独立连接记录失败，避免阻塞失败日志。
            conn.rollback()
            _record_failure(view, f"{type(exc).__name__}: {exc}")
            raise
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (SYNC_LOCK_KEY,))


__all__ = [
    "ViewInfo",
    "ensure_sync_schema",
    "plan_sync",
    "resolve_view",
    "sync_view",
    "validate_view",
]
