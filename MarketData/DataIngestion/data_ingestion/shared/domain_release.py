"""将现有发布版转换为按业务域组织的多字段 Parquet 候选版本。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml


DAILY_BASIC_FIELDS = (
    "total_mv", "float_mv", "total_shares", "float_shares",
    "pe", "pe_ttm", "pb", "ps_ttm",
)
SECURITY_STATUS_FIELDS = (
    "industry_sw", "industry_sw_code", "limit_status", "is_st", "is_suspended",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _combined_field(path: Path, field: str) -> pd.DataFrame:
    schema = pq.read_schema(path)
    columns: list[tuple[str, str]] = []
    for name in schema.names:
        try:
            symbol, logical_field = ast.literal_eval(name)
        except (SyntaxError, ValueError, TypeError):
            continue
        if logical_field == field:
            columns.append((name, symbol))
    if not columns:
        raise KeyError(f"{path} 缺少逻辑字段 {field}")
    metadata = schema.pandas_metadata or {}
    index_columns = metadata.get("index_columns", ["date"])
    index_column = index_columns[0] if index_columns and isinstance(index_columns[0], str) else "date"
    table = pq.read_table(path, columns=[*(name for name, _ in columns), index_column])
    frame = table.replace_schema_metadata({}).to_pandas().set_index(index_column)
    frame.columns = [symbol for _, symbol in columns]
    frame.index = pd.to_datetime(frame.index)
    frame.index.name = "date"
    return frame.sort_index()


def _symbol_map(current_dir: Path, ifind_dir: Path, source_columns: list[str]) -> tuple[dict[str, str], list[str]]:
    stock_info = pd.read_parquet(current_dir / "metadata" / "stock_info.parquet")
    current = {str(symbol).split(".", 1)[0]: str(symbol) for symbol in stock_info["symbol"].dropna()}
    ifind_symbols = pd.read_parquet(ifind_dir / "universe" / "a_share.parquet")["thscode"].astype(str).tolist()
    ifind_by_code: dict[str, list[str]] = {}
    for symbol in ifind_symbols:
        ifind_by_code.setdefault(symbol.split(".", 1)[0], []).append(symbol)
    mapping = {
        code: ifind_by_code[code][0] if len(ifind_by_code.get(code, [])) == 1 else current[code]
        for code in source_columns
    }
    symbols = sorted(set(mapping.values()) | set(ifind_symbols))
    return mapping, symbols


def _write_daily_basic(current_dir: Path, ifind_dir: Path, target: Path, batch_size: int = 1024) -> dict:
    source_fields = tuple(field for field in DAILY_BASIC_FIELDS if field != "pe")
    files = {field: current_dir / "panels" / f"{field}.parquet" for field in source_fields}
    missing = [str(path) for path in files.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"缺少现有基本面字段文件：{missing}")

    source_columns = [name for name in pq.read_schema(files[source_fields[0]]).names if name != "datetime"]
    mapping, symbols = _symbol_map(current_dir, ifind_dir, source_columns)
    ifind_sequence = ifind_dir / "date_sequence" / "date_sequence.parquet"
    ifind_fields = {field: _combined_field(ifind_sequence, field) for field in ("float_mv", "pe", "pb")}
    desired_columns = pd.MultiIndex.from_product((symbols, DAILY_BASIC_FIELDS), names=("symbol", "field"))

    iterators = {
        field: pq.ParquetFile(path).iter_batches(batch_size=batch_size)
        for field, path in files.items()
    }
    temporary = target.with_suffix(".parquet.tmp")
    target.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    rows = 0
    written_dates: list[pd.Timestamp] = []
    try:
        for batches in zip(*(iterators[field] for field in source_fields), strict=True):
            frames: dict[str, pd.DataFrame] = {}
            dates: pd.DatetimeIndex | None = None
            for field, batch in zip(source_fields, batches, strict=True):
                frame = batch.to_pandas()
                frame.columns = [mapping[str(column)] for column in frame.columns]
                frame.index = pd.to_datetime(frame.index)
                frame.index.name = "date"
                frame = frame.reindex(columns=symbols)
                frames[field] = frame
                if dates is None:
                    dates = frame.index
                elif not dates.equals(frame.index):
                    raise ValueError(f"基本面字段 {field} 的日期轴不一致")
            assert dates is not None
            frames["pe"] = pd.DataFrame(np.nan, index=dates, columns=symbols, dtype="float64")
            for field, overlay in ifind_fields.items():
                frames[field].update(overlay.reindex(index=dates, columns=symbols))
            combined = pd.concat(frames, axis=1, names=("field", "symbol")).swaplevel(0, 1, axis=1)
            combined = combined.reindex(columns=desired_columns)
            combined.index.name = "date"
            table = pa.Table.from_pandas(combined, preserve_index=True)
            if writer is None:
                writer = pq.ParquetWriter(temporary, table.schema, compression="zstd")
            writer.write_table(table)
            rows += len(combined)
            written_dates.extend(dates)

        extra_dates = ifind_fields["pe"].index.difference(pd.DatetimeIndex(written_dates)).sort_values()
        if len(extra_dates):
            frames = {
                field: pd.DataFrame(np.nan, index=extra_dates, columns=symbols, dtype="float64")
                for field in DAILY_BASIC_FIELDS
            }
            for field, overlay in ifind_fields.items():
                frames[field].update(overlay.reindex(index=extra_dates, columns=symbols))
            combined = pd.concat(frames, axis=1, names=("field", "symbol")).swaplevel(0, 1, axis=1)
            combined = combined.reindex(columns=desired_columns)
            combined.index.name = "date"
            writer.write_table(pa.Table.from_pandas(combined, preserve_index=True))
            rows += len(combined)
    finally:
        if writer is not None:
            writer.close()
    if rows == 0:
        raise ValueError("daily_basic 没有可写入数据")
    temporary.replace(target)
    return {"rows": rows, "symbols": len(symbols), "fields": list(DAILY_BASIC_FIELDS)}


def _write_security_status(ifind_dir: Path, target: Path) -> dict:
    source = ifind_dir / "date_sequence" / "date_sequence.parquet"
    frames = {
        field: _combined_field(source, field).astype("string")
        for field in ("industry_sw", "industry_sw_code", "limit_status")
    }
    dates = frames["limit_status"].index
    symbols = list(frames["limit_status"].columns)
    frames["is_st"] = pd.DataFrame(pd.NA, index=dates, columns=symbols, dtype="boolean")
    frames["is_suspended"] = frames["limit_status"].apply(
        lambda column: column.str.contains("停牌", na=pd.NA).astype("boolean")
    )
    combined = pd.concat(frames, axis=1, names=("field", "symbol")).swaplevel(0, 1, axis=1)
    desired = pd.MultiIndex.from_product((symbols, SECURITY_STATUS_FIELDS), names=("symbol", "field"))
    combined = combined.reindex(columns=desired)
    combined.index.name = "date"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".parquet.tmp")
    combined.to_parquet(temporary, engine="pyarrow", compression="zstd")
    temporary.replace(target)
    return {"rows": len(combined), "symbols": len(symbols), "fields": list(SECURITY_STATUS_FIELDS)}


def _asset(path: Path, root: Path, summary: dict, sources: dict[str, list[str]]) -> dict:
    return {
        "path": path.relative_to(root).as_posix(),
        **summary,
        "sources": sources,
        "sha256": _sha256(path),
    }


def _copy_sorted_panel(source: Path, target: Path) -> None:
    schema = pq.read_schema(source)
    metadata = schema.pandas_metadata or {}
    index_columns = metadata.get("index_columns", ["date"])
    index_column = index_columns[0] if index_columns and isinstance(index_columns[0], str) else "date"
    dates = pd.DatetimeIndex(pd.to_datetime(pq.read_table(source, columns=[index_column]).column(0).to_pandas()))
    if dates.is_unique and dates.is_monotonic_increasing:
        shutil.copy2(source, target)
        return
    if not dates.is_unique:
        raise ValueError(f"合并面板日期不唯一：{source}")
    table = pq.read_table(source)
    order = pa.array(np.argsort(dates.values, kind="stable"))
    temporary = target.with_suffix(".parquet.tmp")
    pq.write_table(table.take(order), temporary, compression="zstd")
    temporary.replace(target)


def build_domain_release(current_dir: Path, ifind_dir: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"候选发布目录已存在：{output_dir}")
    output_dir.mkdir(parents=True)
    try:
        shutil.copytree(current_dir / "metadata", output_dir / "metadata")
        benchmark_dir = output_dir / "benchmark"
        benchmark_dir.mkdir()
        benchmark_sources = [
            ifind_dir / "index" / "index_price" / "index_price_000300.SH.parquet",
            ifind_dir / "index" / "index_price" / "index_price_000905.SH.parquet",
            ifind_dir / "index" / "index_weights" / "index_weights_000300.SH.parquet",
            ifind_dir / "index" / "index_weights" / "index_weights_000905.SH.parquet",
        ]
        for source in benchmark_sources:
            shutil.copy2(source, benchmark_dir / source.name)
        universe_target = output_dir / "universe" / "a_share.parquet"
        universe_target.parent.mkdir()
        shutil.copy2(ifind_dir / "universe" / "a_share.parquet", universe_target)
        panels = output_dir / "panels"
        panels.mkdir()

        market_target = panels / "market_data.parquet"
        _copy_sorted_panel(ifind_dir / "market_data" / "market_data_hfq.parquet", market_target)
        market_schema = pq.read_schema(market_target)
        market_fields: set[str] = set()
        market_symbols: set[str] = set()
        for name in market_schema.names:
            try:
                symbol, field = ast.literal_eval(name)
            except (SyntaxError, ValueError, TypeError):
                continue
            market_symbols.add(symbol)
            market_fields.add(field)
        market_rows = pq.ParquetFile(market_target).metadata.num_rows

        daily_target = panels / "daily_basic.parquet"
        daily_summary = _write_daily_basic(current_dir, ifind_dir, daily_target)
        status_target = panels / "security_status.parquet"
        status_summary = _write_security_status(ifind_dir, status_target)
        display_target = output_dir / "display" / "unadjusted_price.parquet"
        display_target.parent.mkdir()
        _copy_sorted_panel(ifind_dir / "unadjusted_price" / "unadjusted_price.parquet", display_target)
        display_schema = pq.read_schema(display_target)
        display_pairs: list[tuple[str, str]] = []
        for name in display_schema.names:
            try:
                display_pairs.append(ast.literal_eval(name))
            except (SyntaxError, ValueError, TypeError):
                continue
        display_fields = sorted({field for _, field in display_pairs})
        display_symbols = {symbol for symbol, _ in display_pairs}

        assets = [
            _asset(market_target, output_dir, {
                "rows": market_rows, "symbols": len(market_symbols), "fields": sorted(market_fields),
            }, {field: ["ifind"] for field in sorted(market_fields)}),
            _asset(daily_target, output_dir, daily_summary, {
                "total_mv": ["akshare"], "float_mv": ["akshare", "ifind"],
                "total_shares": ["akshare"], "float_shares": ["akshare"],
                "pe": ["ifind"], "pe_ttm": ["akshare"], "pb": ["akshare", "ifind"],
                "ps_ttm": ["akshare"],
            }),
            _asset(status_target, output_dir, status_summary, {
                "industry_sw": ["ifind"], "industry_sw_code": ["ifind"],
                "limit_status": ["ifind"], "is_st": [], "is_suspended": ["derived:limit_status"],
            }),
            _asset(display_target, output_dir, {
                "rows": pq.ParquetFile(display_target).metadata.num_rows,
                "symbols": len(display_symbols), "fields": display_fields,
            }, {field: ["ifind"] for field in display_fields}),
        ]
        for path in sorted(benchmark_dir.glob("*.parquet")):
            is_weights = path.name.startswith("index_weights_")
            assets.append(_asset(path, output_dir, {
                "rows": pq.ParquetFile(path).metadata.num_rows,
                "symbols": pq.ParquetFile(path).metadata.num_columns - 1 if is_weights else 1,
                "fields": ["weight"] if is_weights else ["open", "high", "low", "close"],
            }, {"weight" if is_weights else "price": ["ifind"]}))
        assets.append(_asset(universe_target, output_dir, {
            "rows": pq.ParquetFile(universe_target).metadata.num_rows,
            "symbols": pq.ParquetFile(universe_target).metadata.num_rows,
            "fields": ["thscode", "name"],
        }, {"thscode": ["ifind"], "name": ["ifind"]}))
        manifest = {
            "schema_version": 2,
            "data_version": output_dir.name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "layout": "domain_multi_field_parquet",
            "missing_value_policy": "原样保留，由研究员在使用阶段处理",
            "assets": assets,
            "release_status": "candidate",
        }
        (output_dir / "data_manifest.yaml").write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        (output_dir / "quality_report.json").write_text(
            json.dumps({"status": "generated", "assets": assets}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--ifind", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_domain_release(args.current, args.ifind, args.output)
    print(json.dumps({"data_version": manifest["data_version"], "assets": len(manifest["assets"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
