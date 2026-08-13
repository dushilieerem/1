"""将 iFinD 日频行情原始 JSON 汇总为完整 CSV，不调用 iFinD。"""

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
from data_ingestion.ifind.market_data.download import LIQUIDITY, PRICE
from data_ingestion.ifind.universe.pipeline import existing_universe_path

WIDE_FIELDS = ("open", "high", "low", "close", "volume", "amount", "turnover")
DEFAULT_WORKERS = max(1, min(4, os.cpu_count() or 1))
OUTPUT_DIR = "market_data"
OUTPUT_FILENAME = "market_data_hfq.csv"


def _date(value: str) -> str:
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"iFinD 返回无效日期：{value}")


def normalize_history_response(group: dict, response: dict, exchange: str) -> list[dict[str, object]]:
    tables = response.get("tables")
    if not isinstance(tables, list):
        raise ValueError("iFinD 历史行情返回缺少 tables")
    rows: list[dict[str, object]] = []
    for item in tables:
        thscode, times, table = item.get("thscode"), item.get("time"), item.get("table")
        if not isinstance(thscode, str) or not isinstance(times, list) or not isinstance(table, dict):
            raise ValueError("iFinD 历史行情单证券结果格式无效")
        if any(not isinstance(table.get(field), list) or len(table[field]) != len(times) for field in group["fields"]):
            raise ValueError(f"iFinD {group['name']} 字段长度不一致：{thscode}")
        for index, raw_date in enumerate(times):
            values = {field: table[field][index] for field in group["fields"]}
            row = {"date": _date(str(raw_date)), "thscode": thscode, "exchange": exchange, "source": "ifind"}
            if group is PRICE:
                row.update(values)
                row["adjustment"] = "hfq"
            else:
                volume, amount, turnover = (values[field] for field in group["fields"])
                row.update({"volume": volume, "amount": amount, "turnover": None if turnover is None else float(turnover) / 100})
            rows.append(row)
    return rows


def _paths(root: Path) -> dict[Path, Path]:
    return {} if not root.is_dir() else {path.relative_to(root): path for path in root.rglob("*.json")}


def _load(path: Path, group: dict, exchange: str) -> dict[tuple[str, str], dict[str, object]]:
    with path.open(encoding="utf-8") as stream:
        rows = normalize_history_response(group, json.load(stream), exchange)
    return {(str(row["date"]), str(row["thscode"])): row for row in rows}


def _merge_partition(job: tuple[Path, Path | None, Path | None]) -> list[dict[str, object]]:
    relative, price_path, liquidity_path = job
    exchange = relative.parts[0]
    prices = _load(price_path, PRICE, exchange) if price_path else {}
    liquidity = _load(liquidity_path, LIQUIDITY, exchange) if liquidity_path else {}
    rows: list[dict[str, object]] = []
    for key in sorted(set(prices) | set(liquidity)):
        price, liquid = prices.get(key, {}), liquidity.get(key, {})
        source = price or liquid
        rows.append({"date": source["date"], "thscode": source["thscode"], "exchange": source["exchange"], **{field: price.get(field, "") for field in ("open", "high", "low", "close", "adjustment")}, **{field: liquid.get(field, "") for field in ("volume", "amount", "turnover")}, "source": "ifind"})
    return rows


def _parallel_merge(jobs: list[tuple[Path, Path | None, Path | None]], workers: int):
    if workers == 1:
        yield from map(_merge_partition, jobs)
        return
    with ProcessPoolExecutor(max_workers=workers) as executor:
        yield from executor.map(_merge_partition, jobs, chunksize=8)


def _jobs_for_date(output_root: Path, as_of: str) -> list[tuple[Path, Path | None, Path | None]]:
    price_paths = {relative: path for relative, path in _paths(output_root.joinpath(*PRICE["raw_root"])).items() if relative.parts[1] == f"{as_of}_{as_of}"}
    liquidity_paths = {relative: path for relative, path in _paths(output_root.joinpath(*LIQUIDITY["raw_root"])).items() if relative.parts[1] == f"{as_of}_{as_of}"}
    return [(relative, price_paths.get(relative), liquidity_paths.get(relative)) for relative in sorted(set(price_paths) | set(liquidity_paths), key=str)]


def _wide_columns(universe_path: Path) -> tuple[str, ...]:
    with universe_path.open(encoding="utf-8-sig", newline="") as stream:
        symbols = [row["thscode"] for row in csv.DictReader(stream)]
    if len(symbols) != len(set(symbols)):
        raise ValueError(f"证券池存在重复证券代码：{universe_path}")
    return ("date", *(f"{symbol}__{field}" for symbol in symbols for field in WIDE_FIELDS))


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
            for field in WIDE_FIELDS:
                value = row.get(field)
                if value not in (None, ""):
                    column = f"{row['thscode']}__{field}"
                    if column in target:
                        raise ValueError(f"原始 JSON 存在重复 date + thscode + field：{row['date']} {column}")
                    target[column] = value
    return result


def build_daily_csv(output_root: Path, workers: int = DEFAULT_WORKERS, universe_path: Path | None = None) -> dict[str, int]:
    if workers <= 0:
        raise ValueError("workers 必须大于零")
    price_paths = _paths(output_root.joinpath(*PRICE["raw_root"]))
    liquidity_paths = _paths(output_root.joinpath(*LIQUIDITY["raw_root"]))
    universe_path = universe_path or existing_universe_path(output_root)
    columns = _wide_columns(universe_path)
    output_path = output_root / OUTPUT_DIR / OUTPUT_FILENAME
    temporary_path = output_path.with_suffix(".csv.tmp")
    summary = {"rows": 0, "partitions": 0}
    partitions = sorted(set(price_paths) | set(liquidity_paths), key=str)
    windows: dict[str, list[tuple[Path, Path | None, Path | None]]] = {}
    for relative in partitions:
        windows.setdefault(relative.parts[1], []).append((relative, price_paths.get(relative), liquidity_paths.get(relative)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with temporary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerows(_headers(columns))
        for window_number, window in enumerate(sorted(windows), start=1):
            jobs = windows[window]
            print(f"[market_data_csv] 第 {window_number}/{len(windows)} 个日期窗口：正在汇总 {window}", flush=True)
            parsed_partitions = list(_parallel_merge(jobs, workers))
            summary["partitions"] += len(parsed_partitions)
            for row in _wide_rows(parsed_partitions).values():
                _write_row(writer, columns, row)
                summary["rows"] += 1
    replace_with_retry(temporary_path, output_path)
    print(f"[market_data_csv] 已完成：{summary['rows']} 行，写入 {output_path}", flush=True)
    return summary


def update_daily_csv_range(
    output_root: Path,
    dates: list[str],
    workers: int = DEFAULT_WORKERS,
    universe_path: Path | None = None,
) -> dict[str, int]:
    """以多个指定日期的 raw JSON 一次性更新完整 CSV，不重解析历史 JSON。"""
    if workers <= 0:
        raise ValueError("workers 必须大于零")
    dates = sorted(set(dates))
    if not dates:
        return {"rows": 0, "replaced_rows": 0, "partitions": 0}
    universe_path = universe_path or existing_universe_path(output_root)
    columns = _wide_columns(universe_path)
    output_path = output_root / OUTPUT_DIR / OUTPUT_FILENAME
    if not output_path.is_file():
        print("[market_data_csv] 完整 CSV 不存在，改为全量重建", flush=True)
        return build_daily_csv(output_root, workers, universe_path)
    with output_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        if tuple(next(reader, [])) != tuple(_headers(columns)[0]) or tuple(next(reader, [])) != tuple(_headers(columns)[1]):
            print("[market_data_csv] 现有 CSV 不是当前宽表结构，改为全量重建", flush=True)
            return build_daily_csv(output_root, workers, universe_path)
    jobs = [job for date in dates for job in _jobs_for_date(output_root, date)]
    partition_rows: list[list[dict[str, object]]] = []
    for number, rows in enumerate(_parallel_merge(jobs, workers), start=1):
        print(f"[market_data_csv] 第 {number}/{len(jobs)} 批：正在解析增量 JSON", flush=True)
        partition_rows.append(rows)
    delta_rows = _wide_rows(partition_rows)
    if not delta_rows:
        print(f"[market_data_csv] 未找到 {dates[0]} 至 {dates[-1]} 的原始 JSON，CSV 不变", flush=True)
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
            if summary["rows"] % 1_000_000 == 0:
                print(f"[market_data_csv] 正在写入历史 CSV：{summary['rows']} 行", flush=True)
        for date in sorted(delta_rows):
            _write_row(writer, columns, delta_rows[date])
            summary["rows"] += 1
    replace_with_retry(temporary_path, output_path)
    print(
        f"[market_data_csv] 已完成区间更新：替换 {len(delta_rows)} 行，写入 {output_path}",
        flush=True,
    )
    return summary


def update_daily_csv(output_root: Path, as_of: str, workers: int = DEFAULT_WORKERS, universe_path: Path | None = None) -> dict[str, int]:
    """以指定日期的 raw JSON 覆盖完整 CSV 中同日记录，不重解析历史 JSON。"""
    return update_daily_csv_range(output_root, [as_of], workers, universe_path)


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
    result = update_daily_csv(args.output_root, args.as_of, args.workers, args.universe) if args.command == "update" else build_daily_csv(args.output_root, args.workers, args.universe)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
