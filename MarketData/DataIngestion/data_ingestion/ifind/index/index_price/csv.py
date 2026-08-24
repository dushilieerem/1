"""将 iFinD 指数 OHLC 原始 JSON 汇总为完整 CSV。"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.index.index_price.download import INDEX_PRICE, OUTPUT_DIR, artifact_path

OUTPUT_FIELDS = ("open", "high", "low", "close")


def _date(value: str) -> str:
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"iFinD 返回无效日期：{value}")


def normalize_index_price_response(response: dict, index_code: str) -> list[dict[str, object]]:
    tables = response.get("tables")
    if not isinstance(tables, list):
        raise ValueError("iFinD 指数价格返回缺少 tables")
    rows: list[dict[str, object]] = []
    for item in tables:
        thscode, times, table = item.get("thscode"), item.get("time"), item.get("table")
        if thscode != index_code or not isinstance(times, list) or not isinstance(table, dict):
            raise ValueError(f"iFinD 指数价格返回格式无效：{index_code}")
        if any(not isinstance(table.get(field), list) or len(table[field]) != len(times) for field in INDEX_PRICE["fields"]):
            raise ValueError(f"iFinD 指数价格字段长度不一致：{index_code}")
        for number, raw_date in enumerate(times):
            rows.append({
                "date": _date(str(raw_date)),
                **{field: table[field][number] for field in OUTPUT_FIELDS},
            })
    return rows


def _raw_paths(output_root: Path, index_code: str) -> list[Path]:
    return sorted((output_root / OUTPUT_DIR / "raw" / index_code).glob("*.json"))


def _raw_paths_for_date(output_root: Path, index_code: str, as_of: str) -> list[Path]:
    paths = []
    for path in _raw_paths(output_root, index_code):
        parts = path.stem.split("_", 1)
        if len(parts) == 2 and parts[0] <= as_of <= parts[1]:
            paths.append(path)
    return paths


def _load_rows(paths: list[Path], index_code: str) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for number, path in enumerate(paths, start=1):
        print(f"[index_price_csv] 第 {number}/{len(paths)} 批：正在汇总 {path.stem}", flush=True)
        with path.open(encoding="utf-8") as stream:
            rows = normalize_index_price_response(json.load(stream), index_code)
        for row in rows:
            date = str(row["date"])
            if date in result:
                raise ValueError(f"指数价格原始 JSON 存在重复日期：{index_code} {date}")
            result[date] = row
    return result


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("date", *OUTPUT_FIELDS))
        writer.writeheader()
        writer.writerows(rows)


def build_index_price_csv(output_root: Path, index_code: str) -> dict[str, int]:
    paths = _raw_paths(output_root, index_code)
    output_path = artifact_path(output_root, index_code, "csv")
    temporary_path = output_path.with_suffix(".csv.tmp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows_by_date = _load_rows(paths, index_code)
    _write_csv(temporary_path, [rows_by_date[date] for date in sorted(rows_by_date)])
    temporary_path.replace(output_path)
    print(f"[index_price_csv] 已完成：{len(rows_by_date)} 行，写入 {output_path}", flush=True)
    return {"rows": len(rows_by_date), "partitions": len(paths)}


def update_index_price_csv_range(
    output_root: Path,
    index_code: str,
    dates: list[str],
) -> dict[str, int]:
    dates = sorted(set(dates))
    if not dates:
        return {"rows": 0, "replaced_rows": 0, "partitions": 0}
    output_path = artifact_path(output_root, index_code, "csv")
    if not output_path.is_file():
        print("[index_price_csv] 完整 CSV 不存在，改为全量重建", flush=True)
        return build_index_price_csv(output_root, index_code)
    paths = sorted({
        path
        for date in dates
        for path in _raw_paths_for_date(output_root, index_code, date)
    })
    loaded_rows = _load_rows(paths, index_code)
    deltas = {date: loaded_rows[date] for date in dates if date in loaded_rows}
    if not deltas:
        print(f"[index_price_csv] 未找到 {dates[0]} 至 {dates[-1]} 的原始 JSON，CSV 不变", flush=True)
        return {"rows": 0, "replaced_rows": 0, "partitions": 0}
    with output_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != ("date", *OUTPUT_FIELDS):
            print("[index_price_csv] 现有 CSV 不是当前结构，改为全量重建", flush=True)
            return build_index_price_csv(output_root, index_code)
        rows = [row for row in reader if row["date"] not in deltas]
    rows.extend(deltas.values())
    rows.sort(key=lambda row: str(row["date"]))
    temporary_path = output_path.with_suffix(".csv.tmp")
    _write_csv(temporary_path, rows)
    temporary_path.replace(output_path)
    print(
        f"[index_price_csv] 已完成区间更新：替换 {len(deltas)} 行，写入 {output_path}",
        flush=True,
    )
    return {"rows": len(rows), "replaced_rows": len(deltas), "partitions": len(paths)}


def update_index_price_csv(output_root: Path, index_code: str, as_of: str) -> dict[str, int]:
    return update_index_price_csv_range(output_root, index_code, [as_of])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("rebuild", "update"), default="rebuild")
    parser.add_argument("--index", default="000300.SH")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of")
    args = parser.parse_args()
    if args.command == "update" and not args.as_of:
        raise SystemExit("update 必须提供 --as-of")
    result = update_index_price_csv(args.output_root, args.index, args.as_of) if args.command == "update" else build_index_price_csv(args.output_root, args.index)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
