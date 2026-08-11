"""将 iFinD 日期序列原始 JSON 汇总为完整 CSV，不调用 iFinD。"""

from __future__ import annotations

import argparse
import csv
import json
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.date_sequence.download import SOURCE_FIELDS
from data_ingestion.ifind.universe.pipeline import existing_universe_path

CSV_FIELDS = ("float_mv", "pe", "pb", "industry_sw", "industry_sw_code", "limit_status")
FIELD_MAP = dict(zip(SOURCE_FIELDS, CSV_FIELDS, strict=True))
CSV_COLUMNS = ("date", "thscode", "exchange", *CSV_FIELDS, "source")
DEFAULT_WORKERS = max(1, min(4, os.cpu_count() or 1))
OUTPUT_DIR = "date_sequence"
OUTPUT_FILENAME = "date_sequence.csv"


def _date(value: str) -> str:
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"iFinD 返回无效日期：{value}")


def normalize_date_sequence_response(response: dict, exchange: str) -> list[dict[str, object]]:
    tables = response.get("tables")
    if not isinstance(tables, list):
        raise ValueError("iFinD 日期序列返回缺少 tables")
    rows: list[dict[str, object]] = []
    for item in tables:
        thscode, times, table = item.get("thscode"), item.get("time"), item.get("table")
        if not isinstance(thscode, str) or not isinstance(times, list) or not isinstance(table, dict):
            raise ValueError("iFinD 日期序列单证券结果格式无效")
        if any(not isinstance(table.get(field), list) or len(table[field]) != len(times) for field in SOURCE_FIELDS):
            raise ValueError(f"iFinD 日期序列字段长度不一致：{thscode}")
        for index, raw_date in enumerate(times):
            rows.append({"date": _date(str(raw_date)), "thscode": thscode, "exchange": exchange, **{target: table[source][index] for source, target in FIELD_MAP.items()}, "source": "ifind"})
    return rows


def _parse_partition(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as raw_stream:
        return normalize_date_sequence_response(json.load(raw_stream), path.parent.parent.name)


def _parallel_parse(paths: list[Path], workers: int):
    if workers == 1:
        yield from map(_parse_partition, paths)
        return
    with ProcessPoolExecutor(max_workers=workers) as executor:
        yield from executor.map(_parse_partition, paths, chunksize=8)


def _paths_for_date(raw_root: Path, as_of: str) -> list[Path]:
    return sorted(path for path in raw_root.rglob("*.json") if path.parent.name == f"{as_of}_{as_of}")


def _wide_columns(universe_path: Path) -> tuple[str, ...]:
    with universe_path.open(encoding="utf-8-sig", newline="") as stream:
        symbols = [row["thscode"] for row in csv.DictReader(stream)]
    if len(symbols) != len(set(symbols)):
        raise ValueError(f"证券池存在重复证券代码：{universe_path}")
    return ("date", *(f"{symbol}__{field}" for symbol in symbols for field in CSV_FIELDS))


def _headers(columns: tuple[str, ...]) -> tuple[list[str], list[str]]:
    symbols, fields = ["date"], [""]
    for column in columns[1:]:
        symbol, field = column.rsplit("__", 1)
        symbols.append(symbol)
        fields.append(field)
    return symbols, fields


def _write_row(writer: csv.writer, columns: tuple[str, ...], row: dict[str, object]) -> None:
    writer.writerow([row["date"], *(row.get(column, "") for column in columns[1:])])


def _wide_rows(partition_rows: list[list[dict[str, object]]]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for rows in partition_rows:
        for row in rows:
            target = result.setdefault(str(row["date"]), {"date": row["date"]})
            for field in CSV_FIELDS:
                value = row[field]
                if value not in (None, ""):
                    column = f"{row['thscode']}__{field}"
                    if column in target:
                        raise ValueError(f"原始 JSON 存在重复 date + thscode + field：{row['date']} {column}")
                    target[column] = value
    return result


def build_date_sequence_csv(output_root: Path, workers: int = DEFAULT_WORKERS, universe_path: Path | None = None) -> dict[str, int]:
    if workers <= 0:
        raise ValueError("workers 必须大于零")
    raw_root = output_root / "date_sequence" / "raw"
    universe_path = universe_path or existing_universe_path(output_root)
    columns = _wide_columns(universe_path)
    output_path = output_root / OUTPUT_DIR / OUTPUT_FILENAME
    temporary_path = output_path.with_suffix(".csv.tmp")
    summary = {"rows": 0, "partitions": 0}
    paths = sorted(raw_root.rglob("*.json"))
    windows: dict[str, list[Path]] = {}
    for path in paths:
        windows.setdefault(path.parent.name, []).append(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with temporary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerows(_headers(columns))
        for number, window in enumerate(sorted(windows), start=1):
            print(f"[date_sequence_csv] 第 {number}/{len(windows)} 个日期窗口：正在汇总 {window}", flush=True)
            parsed_partitions = list(_parallel_parse(windows[window], workers))
            summary["partitions"] += len(parsed_partitions)
            for row in _wide_rows(parsed_partitions).values():
                _write_row(writer, columns, row)
                summary["rows"] += 1
    temporary_path.replace(output_path)
    print(f"[date_sequence_csv] 已完成：{summary['rows']} 行，写入 {output_path}", flush=True)
    return summary


def update_date_sequence_csv(output_root: Path, as_of: str, workers: int = DEFAULT_WORKERS, universe_path: Path | None = None) -> dict[str, int]:
    """以指定日期的 raw JSON 覆盖完整 CSV 中同日记录，不重解析历史 JSON。"""
    if workers <= 0:
        raise ValueError("workers 必须大于零")
    raw_root = output_root / "date_sequence" / "raw"
    universe_path = universe_path or existing_universe_path(output_root)
    columns = _wide_columns(universe_path)
    output_path = output_root / OUTPUT_DIR / OUTPUT_FILENAME
    if not output_path.is_file():
        print("[date_sequence_csv] 完整 CSV 不存在，改为全量重建", flush=True)
        return build_date_sequence_csv(output_root, workers, universe_path)
    with output_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        if tuple(next(reader, [])) != tuple(_headers(columns)[0]) or tuple(next(reader, [])) != tuple(_headers(columns)[1]):
            print("[date_sequence_csv] 现有 CSV 不是当前宽表结构，改为全量重建", flush=True)
            return build_date_sequence_csv(output_root, workers, universe_path)
    paths = _paths_for_date(raw_root, as_of)
    partition_rows: list[list[dict[str, object]]] = []
    for number, rows in enumerate(_parallel_parse(paths, workers), start=1):
        print(f"[date_sequence_csv] 第 {number}/{len(paths)} 批：正在解析 {as_of} 的增量 JSON", flush=True)
        partition_rows.append(rows)
    delta = _wide_rows(partition_rows).get(as_of)
    if delta is None:
        print(f"[date_sequence_csv] 未找到 {as_of} 的原始 JSON，CSV 不变", flush=True)
        return {"rows": 0, "replaced_rows": 0, "partitions": len(paths)}
    temporary_path = output_path.with_suffix(".csv.tmp")
    summary = {"rows": 0, "replaced_rows": 1, "partitions": len(paths)}
    with output_path.open(encoding="utf-8-sig", newline="") as source, temporary_path.open("w", encoding="utf-8", newline="") as target:
        reader = csv.reader(source)
        next(reader, None)
        next(reader, None)
        writer = csv.writer(target)
        writer.writerows(_headers(columns))
        for row in reader:
            if row and row[0] == as_of:
                continue
            writer.writerow(row)
            summary["rows"] += 1
            if summary["rows"] % 1_000_000 == 0:
                print(f"[date_sequence_csv] 正在写入历史 CSV：{summary['rows']} 行", flush=True)
        _write_row(writer, columns, delta)
        summary["rows"] += 1
    temporary_path.replace(output_path)
    print(f"[date_sequence_csv] 已完成当日更新：替换 1 行，写入 {output_path}", flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("rebuild", "update"), default="rebuild")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--as-of", help="日增量目标日，格式 YYYY-MM-DD")
    parser.add_argument("--universe", type=Path)
    args = parser.parse_args()
    if args.command == "update" and not args.as_of:
        raise SystemExit("update 必须提供 --as-of")
    result = update_date_sequence_csv(args.output_root, args.as_of, args.workers, args.universe) if args.command == "update" else build_date_sequence_csv(args.output_root, args.workers, args.universe)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
