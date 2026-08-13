"""将 iFinD 未复权 OHLC 原始 JSON 汇总为完整 CSV，不调用 iFinD。"""

from __future__ import annotations

import argparse
import csv
import json
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.common.file_ops import replace_with_retry
from data_ingestion.ifind.unadjusted_price.download import PRICE
from data_ingestion.ifind.universe.pipeline import existing_universe_path

FIELDS = ("open", "high", "low", "close")
DEFAULT_WORKERS = max(1, min(4, os.cpu_count() or 1))
OUTPUT_DIR = "unadjusted_price"
OUTPUT_FILENAME = "unadjusted_price.csv"


def _date(value: str) -> str:
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"iFinD 返回无效日期：{value}")


def normalize_history_response(response: dict) -> list[dict[str, object]]:
    tables = response.get("tables")
    if not isinstance(tables, list):
        raise ValueError("iFinD 未复权行情返回缺少 tables")
    rows: list[dict[str, object]] = []
    for item in tables:
        thscode, times, table = item.get("thscode"), item.get("time"), item.get("table")
        if not isinstance(thscode, str) or not isinstance(times, list) or not isinstance(table, dict):
            raise ValueError("iFinD 未复权行情单证券结果格式无效")
        if any(not isinstance(table.get(field), list) or len(table[field]) != len(times) for field in FIELDS):
            raise ValueError(f"iFinD 未复权行情字段长度不一致：{thscode}")
        for index, raw_date in enumerate(times):
            rows.append({
                "date": _date(str(raw_date)),
                "thscode": thscode,
                **{field: table[field][index] for field in FIELDS},
            })
    return rows


def _paths(root: Path) -> dict[Path, Path]:
    return {} if not root.is_dir() else {path.relative_to(root): path for path in root.rglob("*.json")}


def _load(job: tuple[Path, Path]) -> list[dict[str, object]]:
    _, path = job
    with path.open(encoding="utf-8") as stream:
        return normalize_history_response(json.load(stream))


def _parallel_load(jobs: list[tuple[Path, Path]], workers: int):
    if workers == 1:
        yield from map(_load, jobs)
        return
    with ProcessPoolExecutor(max_workers=workers) as executor:
        yield from executor.map(_load, jobs, chunksize=8)


def _wide_columns(universe_path: Path) -> tuple[str, ...]:
    with universe_path.open(encoding="utf-8-sig", newline="") as stream:
        symbols = [row["thscode"] for row in csv.DictReader(stream)]
    if len(symbols) != len(set(symbols)):
        raise ValueError(f"证券池存在重复证券代码：{universe_path}")
    return ("date", *(f"{symbol}__{field}" for symbol in symbols for field in FIELDS))


def _headers(columns: tuple[str, ...]) -> tuple[list[str], list[str]]:
    symbols, fields = ["date"], [""]
    for column in columns[1:]:
        symbol, field = column.rsplit("__", 1)
        symbols.append(symbol)
        fields.append(field)
    return symbols, fields


def _wide_rows(partition_rows: list[list[dict[str, object]]]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for rows in partition_rows:
        for row in rows:
            target = result.setdefault(str(row["date"]), {"date": row["date"]})
            for field in FIELDS:
                value = row.get(field)
                if value not in (None, ""):
                    column = f"{row['thscode']}__{field}"
                    if column in target:
                        raise ValueError(f"原始 JSON 存在重复 date + thscode + field：{row['date']} {column}")
                    target[column] = value
    return result


def _write_row(writer: csv.writer, columns: tuple[str, ...], row: dict[str, object]) -> None:
    writer.writerow([row["date"], *(row.get(column, "") for column in columns[1:])])


def _jobs_for_date(output_root: Path, as_of: str) -> list[tuple[Path, Path]]:
    paths = _paths(output_root.joinpath(*PRICE["raw_root"]))
    return [(relative, path) for relative, path in sorted(paths.items(), key=lambda item: str(item[0])) if relative.parts[1] == f"{as_of}_{as_of}"]


def build_price_csv(output_root: Path, workers: int = DEFAULT_WORKERS, universe_path: Path | None = None) -> dict[str, int]:
    if workers <= 0:
        raise ValueError("workers 必须大于零")
    paths = _paths(output_root.joinpath(*PRICE["raw_root"]))
    universe_path = universe_path or existing_universe_path(output_root)
    columns = _wide_columns(universe_path)
    output_path = output_root / OUTPUT_DIR / OUTPUT_FILENAME
    temporary_path = output_path.with_suffix(".csv.tmp")
    windows: dict[str, list[tuple[Path, Path]]] = {}
    for relative, path in paths.items():
        windows.setdefault(relative.parts[1], []).append((relative, path))
    summary = {"rows": 0, "partitions": 0}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with temporary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerows(_headers(columns))
        for window_number, window in enumerate(sorted(windows), start=1):
            jobs = sorted(windows[window], key=lambda item: str(item[0]))
            print(f"[unadjusted_price_csv] 第 {window_number}/{len(windows)} 个日期窗口：正在汇总 {window}", flush=True)
            parsed = list(_parallel_load(jobs, workers))
            summary["partitions"] += len(parsed)
            for row in _wide_rows(parsed).values():
                _write_row(writer, columns, row)
                summary["rows"] += 1
    replace_with_retry(temporary_path, output_path)
    print(f"[unadjusted_price_csv] 已完成：{summary['rows']} 行，写入 {output_path}", flush=True)
    return summary


def update_price_csv_range(
    output_root: Path,
    dates: list[str],
    workers: int = DEFAULT_WORKERS,
    universe_path: Path | None = None,
) -> dict[str, int]:
    if workers <= 0:
        raise ValueError("workers 必须大于零")
    dates = sorted(set(dates))
    if not dates:
        return {"rows": 0, "replaced_rows": 0, "partitions": 0}
    universe_path = universe_path or existing_universe_path(output_root)
    columns = _wide_columns(universe_path)
    output_path = output_root / OUTPUT_DIR / OUTPUT_FILENAME
    if not output_path.is_file():
        print("[unadjusted_price_csv] 完整 CSV 不存在，改为全量重建", flush=True)
        return build_price_csv(output_root, workers, universe_path)
    with output_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        if tuple(next(reader, [])) != tuple(_headers(columns)[0]) or tuple(next(reader, [])) != tuple(_headers(columns)[1]):
            print("[unadjusted_price_csv] 现有 CSV 不是当前宽表结构，改为全量重建", flush=True)
            return build_price_csv(output_root, workers, universe_path)
    jobs = [job for trade_date in dates for job in _jobs_for_date(output_root, trade_date)]
    parsed = list(_parallel_load(jobs, workers))
    delta_rows = _wide_rows(parsed)
    if not delta_rows:
        print(f"[unadjusted_price_csv] 未找到 {dates[0]} 至 {dates[-1]} 的原始 JSON，CSV 不变", flush=True)
        return {"rows": 0, "replaced_rows": 0, "partitions": len(jobs)}
    temporary_path = output_path.with_suffix(".csv.tmp")
    summary = {"rows": 0, "replaced_rows": len(delta_rows), "partitions": len(jobs)}
    with output_path.open(encoding="utf-8-sig", newline="") as source, temporary_path.open("w", encoding="utf-8", newline="") as target:
        reader = csv.reader(source)
        next(reader, None)
        next(reader, None)
        writer = csv.writer(target)
        writer.writerows(_headers(columns))
        for row in reader:
            if row and row[0] in delta_rows:
                continue
            writer.writerow(row)
            summary["rows"] += 1
        for trade_date in sorted(delta_rows):
            _write_row(writer, columns, delta_rows[trade_date])
            summary["rows"] += 1
    replace_with_retry(temporary_path, output_path)
    print(
        f"[unadjusted_price_csv] 已完成区间更新：替换 {len(delta_rows)} 行，写入 {output_path}",
        flush=True,
    )
    return summary


def update_price_csv(output_root: Path, as_of: str, workers: int = DEFAULT_WORKERS, universe_path: Path | None = None) -> dict[str, int]:
    return update_price_csv_range(output_root, [as_of], workers, universe_path)


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
    result = update_price_csv(args.output_root, args.as_of, args.workers, args.universe) if args.command == "update" else build_price_csv(args.output_root, args.workers, args.universe)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
