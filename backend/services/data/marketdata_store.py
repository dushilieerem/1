# -*- coding: utf-8 -*-
"""本地 marketdata release 只读访问（P1-D01/D02/D03/D08）。

数据由 iFinD 同步发布为宽表 Parquet（date × symbol × field），
研究服务与研究库共享同一 release。本模块只读、按列投影，避免把全市场载入内存。

配置：MARKETDATA_DIR（默认仓库同级的 ../marketdata）。
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any

from services.core.env_config import env

_SYMBOL_RE = re.compile(r"^(\d{6})(?:\.(SH|SZ|BJ))?$", re.I)
_lock = threading.Lock()
_manifest_cache: dict[str, Any] = {"at": 0.0, "data": None}

FUNDAMENTAL_FIELDS = {
    "pe_ttm": ("ths_pe_ttm_stock", "市盈率 TTM"),
    "pb_mrq": ("ths_pb_mrq_stock", "市净率 MRQ"),
    "current_mv": ("ths_current_mv_stock", "总市值"),
    "dividend_yield_ttm": ("ths_dividend_yield_ttm_stock", "股息率 TTM"),
    "pcf_operating_cash_flow_ttm": ("ths_pcf_operating_cash_flow_ttm_stock", "经营现金流 P/CF"),
    "listed_status": ("ths_listed_status_stock", "上市状态"),
    "sw_industry_code": ("ths_the_sw_industry_code_stock", "申万行业代码"),
    "up_and_down_status": ("ths_up_and_down_status_stock", "涨跌停状态"),
}


def data_root() -> Path:
    raw = (env("MARKETDATA_DIR", "") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    project_root = Path(__file__).resolve().parents[3].parent
    return (project_root / "marketdata").resolve()


def normalize_symbol(raw: str) -> str:
    """`000001`/`000001.sz` → `000001.SZ`；无法识别抛 ValueError。"""
    text = (raw or "").strip().upper()
    m = _SYMBOL_RE.match(text)
    if not m:
        raise ValueError("证券代码格式错误，应为 000001.SZ 或 000001")
    code, suffix = m.group(1), (m.group(2) or "").upper()
    if not suffix:
        if code.startswith(("6", "9")):
            suffix = "SH"
        elif code.startswith(("4", "8")):
            suffix = "BJ"
        else:
            suffix = "SZ"
    return f"{code}.{suffix}"


def _col(symbol: str, field: str) -> str:
    return f"('{symbol}', '{field}')"


def _read_columns(path: Path, columns: list[str]) -> Any:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - 部署环境应安装 pyarrow
        raise RuntimeError("服务端未安装 pyarrow，无法读取本地行情数据") from exc
    if not path.exists():
        raise FileNotFoundError(str(path))
    return pq.read_table(path, columns=columns)


def data_manifest(max_age_sec: int = 60) -> dict[str, Any]:
    """release 版本与生成时间（P1-D02 数据版本）。"""
    root = data_root()
    path = root / "data_manifest.yaml"
    now = time.time()
    with _lock:
        if _manifest_cache["data"] is not None and now - _manifest_cache["at"] < max_age_sec:
            return dict(_manifest_cache["data"])
    out: dict[str, Any] = {
        "root": str(root),
        "available": root.exists(),
        "data_version": None,
        "generated_at": None,
        "assets": 0,
    }
    if path.exists():
        try:
            import yaml

            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            out.update(
                {
                    "data_version": raw.get("data_version"),
                    "generated_at": raw.get("generated_at"),
                    "assets": len(raw.get("assets") or []),
                }
            )
        except Exception as exc:  # noqa: BLE001
            out["error"] = str(exc)
    with _lock:
        _manifest_cache.update({"at": now, "data": out})
    return dict(out)


def _daily_panel(source: str, symbol: str, fields: list[str], start: str, end: str) -> dict[str, Any]:
    root = data_root()
    path = root / source
    cols = [_col(symbol, f) for f in fields]
    names = ["date", *cols]
    table = _read_columns(path, names)
    data = table.to_pydict()
    items: list[dict[str, Any]] = []
    for i, day in enumerate(data.get("date") or []):
        d = str(day)
        if start and d < start:
            continue
        if end and d > end:
            continue
        row: dict[str, Any] = {"date": d}
        has_value = False
        for f in fields:
            vals = data.get(_col(symbol, f)) or []
            v = vals[i] if i < len(vals) else None
            if v is not None:
                has_value = True
            row[f] = v
        if has_value:
            items.append(row)
    return {"items": items, "count": len(items), **data_manifest()}


def fundamentals(symbol: str, *, start: str = "", end: str = "") -> dict[str, Any]:
    """点时基本面/估值字段（字段来自 date_sequence release）。"""
    sym = normalize_symbol(symbol)
    fields = [f for f, _label in FUNDAMENTAL_FIELDS.values()]
    out = _daily_panel("date_sequence/date_sequence.parquet", sym, fields, start, end)
    rename = {raw: friendly for friendly, (raw, _label) in FUNDAMENTAL_FIELDS.items()}
    out["items"] = [
        {rename.get(k, k): v for k, v in row.items()} for row in out["items"]
    ]
    out["symbol"] = sym
    out["field_labels"] = {k: label for k, (_f, label) in FUNDAMENTAL_FIELDS.items()}
    out["note"] = "当前 release 提供估值/状态字段；财务三表与公告日点时数据待数据源发布"
    return out


def daily_bars(
    symbol: str, *, start: str = "", end: str = "", adjusted: bool = True
) -> dict[str, Any]:
    sym = normalize_symbol(symbol)
    source = (
        "market_data/market_data_hfq.parquet"
        if adjusted
        else "unadjusted_price/unadjusted_price.parquet"
    )
    fields = ["open", "high", "low", "close"] + (["volume", "amount"] if adjusted else [])
    out = _daily_panel(source, sym, fields, start, end)
    out.update({"symbol": sym, "frequency": "1d", "adjusted": adjusted})
    return out


def _minute_files(start: str, end: str) -> list[Path]:
    root = data_root() / "high_frequency" / "1min"
    if not root.exists():
        return []
    files: list[Path] = []
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        year = year_dir.name
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue
            for f in sorted(month_dir.glob("*.parquet")):
                # 文件名 9.10.parquet → 2026-09-10
                parts = f.stem.split(".")
                if len(parts) != 2 or not all(p.isdigit() for p in parts):
                    continue
                day = f"{year}-{int(parts[0]):02d}-{int(parts[1]):02d}"
                if start and day < start:
                    continue
                if end and day > end:
                    continue
                files.append(f)
    return files


MINUTE_FREQS = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}


def resample_minute_bars(items: list[dict[str, Any]], freq: str) -> list[dict[str, Any]]:
    """把 1m bars 按固定分钟聚合（OHLCV）；时间取桶内第一根。"""
    minutes = MINUTE_FREQS.get(str(freq or "1m").lower())
    if minutes is None:
        raise ValueError(f"不支持的分钟频率: {freq}（可选 {', '.join(MINUTE_FREQS)}）")
    if minutes <= 1:
        return items
    out: list[dict[str, Any]] = []
    bucket: dict[str, Any] | None = None
    bucket_index: int | None = None
    for bar in items:
        raw = str(bar.get("time") or "")
        try:
            hh = int(raw[11:13])
            mm = int(raw[14:16])
            idx = (hh * 60 + mm) // minutes
        except (ValueError, IndexError):
            idx = None
        if bucket is None or idx != bucket_index:
            if bucket is not None:
                out.append(bucket)
            bucket = {
                "time": raw,
                "open": bar.get("open"),
                "high": bar.get("high"),
                "low": bar.get("low"),
                "close": bar.get("close"),
                "volume": bar.get("volume"),
                "amount": bar.get("amount"),
            }
            bucket_index = idx
        else:
            if bar.get("high") is not None:
                bucket["high"] = (
                    bar["high"] if bucket["high"] is None else max(bucket["high"], bar["high"])
                )
            if bar.get("low") is not None:
                bucket["low"] = (
                    bar["low"] if bucket["low"] is None else min(bucket["low"], bar["low"])
                )
            bucket["close"] = bar.get("close")
            for key in ("volume", "amount"):
                if bar.get(key) is not None:
                    bucket[key] = (bucket.get(key) or 0) + bar[key]
    if bucket is not None:
        out.append(bucket)
    return out


def minute_bars(
    symbol: str,
    *,
    start: str = "",
    end: str = "",
    limit_days: int = 5,
    freq: str = "1m",
) -> dict[str, Any]:
    """分钟行情（1m 分区读取，可按 freq 聚合；默认最多 5 个交易日）。"""
    if str(freq or "1m").lower() not in MINUTE_FREQS:
        raise ValueError(f"不支持的分钟频率: {freq}（可选 {', '.join(MINUTE_FREQS)}）")
    sym = normalize_symbol(symbol)
    files = _minute_files(start, end)
    if len(files) > limit_days:
        files = files[-limit_days:]
    if not files:
        return {
            "ok": True,
            "symbol": sym,
            "frequency": str(freq or "1m").lower(),
            "items": [],
            "count": 0,
            "note": "指定区间没有分钟数据分区",
            **data_manifest(),
        }
    fields = ["open", "high", "low", "close", "volume", "amount"]
    cols = ["date", *[_col(sym, f) for f in fields]]
    items: list[dict[str, Any]] = []
    for path in files:
        table = _read_columns(path, cols)
        data = table.to_pydict()
        for i, ts in enumerate(data.get("date") or []):
            row: dict[str, Any] = {"time": str(ts)}
            has_value = False
            for f in fields:
                vals = data.get(_col(sym, f)) or []
                v = vals[i] if i < len(vals) else None
                if v is not None:
                    has_value = True
                row[f] = v
            if has_value:
                items.append(row)
    items = resample_minute_bars(items, freq)
    return {
        "ok": True,
        "symbol": sym,
        "frequency": str(freq or "1m").lower(),
        "items": items,
        "count": len(items),
        "days": [p.stem for p in files],
        **data_manifest(),
    }


def index_catalog() -> dict[str, Any]:
    """P1-D03：从 release 动态列出已有指数（替代前端静态样例）。"""
    # P1-O06：跨实例共享缓存；数据库不可用时直接读盘
    try:
        from services.core import shared_cache

        cached = shared_cache.get("marketdata:index_catalog")
        if isinstance(cached, dict) and cached.get("items") is not None:
            return cached
    except Exception:
        cached = None
    root = data_root() / "index" / "index_price"
    items: list[dict[str, Any]] = []
    if root.exists():
        for path in sorted(root.glob("index_price_*.parquet")):
            code = path.stem.replace("index_price_", "")
            items.append(
                {
                    "code": code,
                    "key": code.split(".")[0],
                    "source": "marketdata",
                    "weight_file": (root.parent / "index_weights" / f"index_weights_{code}.parquet").exists(),
                }
            )
    out = {"ok": True, "items": items, "count": len(items), **data_manifest()}
    try:
        from services.core import shared_cache

        shared_cache.set("marketdata:index_catalog", out, ttl_sec=300)
    except Exception:
        pass
    return out


def field_catalog_samples(limit: int = 3) -> dict[str, Any]:
    """P1-D08：字段字典真实样例（取 release 最近一行）。"""
    root = data_root()
    out: dict[str, Any] = {"ok": True, "fields": {}, **data_manifest()}
    if not root.exists():
        return out
    samples: dict[str, Any] = {}
    try:
        table = _read_columns(
            root / "date_sequence/date_sequence.parquet",
            ["date", _col("000001.SZ", "ths_pe_ttm_stock"), _col("000001.SZ", "ths_pb_mrq_stock")],
        )
        data = table.to_pydict()
        idx = len(data.get("date") or []) - 1
        if idx >= 0:
            samples = {
                "date": data["date"][idx],
                "pe_ttm": data[_col("000001.SZ", "ths_pe_ttm_stock")][idx],
                "pb_mrq": data[_col("000001.SZ", "ths_pb_mrq_stock")][idx],
                "symbol": "000001.SZ",
            }
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    out["fields"] = samples
    out["limit"] = max(1, int(limit))
    return out
