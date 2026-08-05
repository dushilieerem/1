"""将 AkShare 日线原始 CSV 转换为候选标准 Parquet 发布版本。"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import pandas as pd
import yaml

from data_ingestion.shared.panel_quality import inspect_panels


FIELD_MAP = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "amount": "amount",
    "turnover": "turn",
}

VALUATION_FIELD_MAP = {
    "total_mv": "total_mv",
    "float_mv": "circ_mv",
    "total_shares": "total_shares",
    "float_shares": "float_shares",
    "pe_ttm": "pe_ttm",
    "pb": "pb",
    "ps_ttm": "ps_ttm",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def publish_daily_bars(
    bars_dir: Path,
    output_dir: Path,
    symbols: Sequence[str],
    *,
    start: str,
    end: str,
    data_version: str,
) -> dict:
    """将指定证券转换为候选发布版本；不覆盖已有输出。"""
    if output_dir.exists():
        raise FileExistsError(f"候选发布目录已存在：{output_dir}")
    if not symbols:
        raise ValueError("至少需要一个证券代码")

    start_at, end_at = pd.Timestamp(start), pd.Timestamp(end)
    panels_dir = output_dir / "panels"
    panels_dir.mkdir(parents=True)
    source_symbols: dict[str, set[str]] = {}
    missing_symbols: dict[str, list[str]] = {}
    assets = []
    calendar_index: pd.DatetimeIndex | None = None

    for standard_field, source_column in FIELD_MAP.items():
        series_by_symbol: dict[str, pd.Series] = {}
        for symbol in symbols:
            path = bars_dir / f"{symbol}.csv"
            if not path.is_file():
                raise FileNotFoundError(f"缺少证券日线文件：{path}")
            required = {"date", source_column, "source"}
            frame = pd.read_csv(path, usecols=lambda column: column in required)
            if source_column not in frame:
                missing_symbols.setdefault(standard_field, []).append(symbol)
                series_by_symbol[symbol.split(".", 1)[0]] = pd.Series(dtype="float64")
                continue
            frame["date"] = pd.to_datetime(frame["date"])
            frame = frame[(frame["date"] >= start_at) & (frame["date"] <= end_at)]
            if frame.empty:
                raise ValueError(f"{path.name} 在指定区间没有数据")
            if frame["date"].duplicated().any():
                raise ValueError(f"{path.name} 存在重复日期")
            for source in frame["source"].dropna().unique():
                source_symbols.setdefault(str(source), set()).add(symbol)
            series_by_symbol[symbol.split(".", 1)[0]] = frame.set_index("date")[source_column]

        panel = pd.DataFrame(series_by_symbol).sort_index().sort_index(axis=1)
        panel.index.name = "datetime"
        if calendar_index is None:
            calendar_index = panel.index
        else:
            panel = panel.reindex(calendar_index)
            panel.index.name = "datetime"
        target = panels_dir / f"{standard_field}.parquet"
        panel.to_parquet(target)
        assets.append({
            "field": standard_field,
            "path": f"panels/{target.name}",
            "sha256": _sha256(target),
            "date_range": [str(panel.index.min().date()), str(panel.index.max().date())],
            "symbol_count": len(panel.columns),
            "status": "ready",
        })

    quality = inspect_panels(panels_dir)
    (output_dir / "quality_report.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest = {
        "schema_version": 1,
        "data_version": data_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "AkShare / Baostock 历史原始库",
        "price_adjustment": "hfq",
        "source_symbol_counts": {source: len(items) for source, items in source_symbols.items()},
        "missing_symbols_by_field": missing_symbols,
        "missing_value_policy": "保留为 NaN；禁止以零值、前值或其他来源补齐",
        "assets": assets,
        "quality_report": "quality_report.json",
        "release_status": "candidate",
    }
    (output_dir / "data_manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return manifest


def append_valuation_panels(
    valuation_dir: Path,
    release_dir: Path,
    symbols: Sequence[str],
) -> dict:
    """向完整候选版本追加可直接映射的日频估值与市值字段。"""
    manifest_path = release_dir / "data_manifest.yaml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"候选版本缺少清单：{manifest_path}")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("release_status") != "candidate":
        raise ValueError("只能扩展 candidate 状态的数据版本")
    if not symbols:
        raise ValueError("至少需要一个证券代码")

    panels_dir = release_dir / "panels"
    calendar_index = pd.DatetimeIndex(pd.read_parquet(panels_dir / "open.parquet").index)
    existing_fields = {asset["field"] for asset in manifest["assets"]}
    overlap = existing_fields & set(VALUATION_FIELD_MAP)
    if overlap:
        raise ValueError(f"候选版本已包含估值字段：{sorted(overlap)}")

    source_symbols: dict[str, set[str]] = {}
    missing_symbols: dict[str, list[str]] = {}
    assets = []
    for standard_field, source_column in VALUATION_FIELD_MAP.items():
        series_by_symbol: dict[str, pd.Series] = {}
        for symbol in symbols:
            path = valuation_dir / f"{symbol}.csv"
            code = symbol.split(".", 1)[0]
            if not path.is_file():
                missing_symbols.setdefault(standard_field, []).append(symbol)
                series_by_symbol[code] = pd.Series(dtype="float64")
                continue
            frame = pd.read_csv(path, usecols=lambda column: column in {"date", source_column, "source"})
            if source_column not in frame:
                missing_symbols.setdefault(standard_field, []).append(symbol)
                series_by_symbol[code] = pd.Series(dtype="float64")
                continue
            frame["date"] = pd.to_datetime(frame["date"])
            if frame["date"].duplicated().any():
                raise ValueError(f"{path.name} 存在重复日期")
            for source in frame["source"].dropna().unique():
                source_symbols.setdefault(str(source), set()).add(symbol)
            series_by_symbol[code] = frame.set_index("date")[source_column]

        panel = pd.DataFrame(series_by_symbol).reindex(calendar_index).sort_index(axis=1)
        panel.index.name = "datetime"
        target = panels_dir / f"{standard_field}.parquet"
        panel.to_parquet(target)
        assets.append({
            "field": standard_field,
            "path": f"panels/{target.name}",
            "sha256": _sha256(target),
            "date_range": [str(panel.index.min().date()), str(panel.index.max().date())],
            "symbol_count": len(panel.columns),
            "status": "ready",
        })

    manifest["assets"].extend(assets)
    for source, items in source_symbols.items():
        manifest["source_symbol_counts"][source] = len(items)
    manifest.setdefault("missing_symbols_by_field", {}).update(missing_symbols)
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    quality = inspect_panels(panels_dir, metadata_dir=release_dir)
    (release_dir / "quality_report.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def _parse_args() -> argparse.Namespace:
    market_data_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    symbol_source = parser.add_mutually_exclusive_group(required=True)
    symbol_source.add_argument("--symbols-file", type=Path)
    symbol_source.add_argument("--all-symbols", action="store_true")
    parser.add_argument("--append-valuations", action="store_true")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--bars-dir", type=Path,
        default=market_data_root / "sources" / "akshare" / "03_market" / "daily" / "bars_hfq",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    market_data_root = Path(__file__).resolve().parents[3]
    if args.all_symbols:
        symbols = [path.stem for path in sorted(args.bars_dir.glob("*.csv"))]
    else:
        symbols = [line.strip() for line in args.symbols_file.read_text(encoding="utf-8").splitlines()]
        symbols = [symbol for symbol in symbols if symbol and not symbol.startswith("#")]
    if args.append_valuations:
        valuation_dir = market_data_root / "sources" / "akshare" / "05_fundamental" / "valuation" / "wide"
        manifest = append_valuation_panels(valuation_dir, args.output, symbols)
        print(f"已追加估值字段：候选版本共有 {len(manifest['assets'])} 个字段")
    else:
        manifest = publish_daily_bars(
            args.bars_dir, args.output, symbols,
            start=args.start, end=args.end, data_version=args.data_version,
        )
        print(f"已生成候选版本 {manifest['data_version']}：{len(manifest['assets'])} 个字段")


if __name__ == "__main__":
    main()
