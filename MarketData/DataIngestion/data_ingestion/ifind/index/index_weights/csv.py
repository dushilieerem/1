"""将 iFinD 指数成分股权重原始 JSON 汇总为日期 × 股票宽表 CSV。"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.index.index_weights.download import OUTPUT_DIR, OUTPUT_FIELDS, artifact_path

SYMBOL_FIELD, WEIGHT_FIELD = OUTPUT_FIELDS


def _table_rows(table: dict) -> list[dict[str, object]]:
    if all(isinstance(table.get(field), list) for field in OUTPUT_FIELDS):
        lengths = {len(table[field]) for field in OUTPUT_FIELDS}
        if len(lengths) != 1:
            raise ValueError("iFinD 指数权重返回字段长度不一致")
        return [{field: table[field][number] for field in OUTPUT_FIELDS} for number in range(lengths.pop())]
    columns, rows = table.get("columns"), table.get("data")
    if isinstance(columns, list) and isinstance(rows, list):
        return [dict(zip(columns, row, strict=True)) for row in rows if isinstance(row, list)]
    raise ValueError("iFinD 指数权重返回格式无法识别；请保留该原始 JSON 并核对接口返回")


def normalize_index_weights_response(response: dict, date: str, index_code: str) -> list[dict[str, object]]:
    candidate = response.get("data", response)
    tables = candidate.get("tables") if isinstance(candidate, dict) else None
    if isinstance(tables, list):
        rows = [row for item in tables if isinstance(item, dict) and isinstance(item.get("table"), dict) for row in _table_rows(item["table"])]
    elif isinstance(candidate, dict):
        rows = _table_rows(candidate)
    elif isinstance(candidate, list):
        rows = [row for item in candidate if isinstance(item, dict) for row in _table_rows(item)]
    else:
        raise ValueError("iFinD 指数权重返回缺少数据表")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in rows:
        symbol = row.get(SYMBOL_FIELD)
        if not isinstance(symbol, str) or not symbol:
            raise ValueError(f"iFinD 指数权重返回无效证券代码：{index_code} {date}")
        if symbol in seen:
            raise ValueError(f"iFinD 指数权重返回重复证券代码：{index_code} {date} {symbol}")
        seen.add(symbol)
        normalized.append({"date": date, "thscode": symbol, "weight": row.get(WEIGHT_FIELD, "")})
    return normalized


def _raw_paths(output_root: Path, index_code: str) -> list[Path]:
    return sorted((output_root / OUTPUT_DIR / "raw" / index_code).glob("*.json"))


def _wide_rows(paths: list[Path], index_code: str) -> tuple[list[str], list[dict[str, object]]]:
    symbols: set[str] = set()
    rows: list[dict[str, object]] = []
    for number, path in enumerate(paths, start=1):
        print(f"[index_weights_csv] 第 {number}/{len(paths)} 日：正在汇总 {path.stem}", flush=True)
        with path.open(encoding="utf-8") as raw_stream:
            normalized = normalize_index_weights_response(json.load(raw_stream), path.stem, index_code)
        row: dict[str, object] = {"date": path.stem}
        for item in normalized:
            symbol = str(item["thscode"])
            symbols.add(symbol)
            row[symbol] = item["weight"]
        rows.append(row)
    return sorted(symbols), rows


def _write_wide_csv(path: Path, symbols: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("date", *symbols))
        writer.writeheader()
        writer.writerows(rows)


def build_index_weights_csv(output_root: Path, index_code: str) -> dict[str, int]:
    paths = _raw_paths(output_root, index_code)
    output_path = artifact_path(output_root, index_code, "csv")
    temporary_path = output_path.with_suffix(".csv.tmp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    symbols, rows = _wide_rows(paths, index_code)
    summary = {"rows": len(rows), "partitions": len(paths)}
    _write_wide_csv(temporary_path, symbols, rows)
    temporary_path.replace(output_path)
    print(f"[index_weights_csv] 已完成：{summary['rows']} 行，写入 {output_path}", flush=True)
    return summary


def update_index_weights_csv_range(
    output_root: Path,
    index_code: str,
    dates: list[str],
) -> dict[str, int]:
    dates = sorted(set(dates))
    if not dates:
        return {"rows": 0, "replaced_rows": 0, "partitions": 0}
    output_path = artifact_path(output_root, index_code, "csv")
    if not output_path.is_file():
        print("[index_weights_csv] 完整 CSV 不存在，改为全量重建", flush=True)
        return build_index_weights_csv(output_root, index_code)
    raw_files = [
        output_root / OUTPUT_DIR / "raw" / index_code / f"{date}.json"
        for date in dates
    ]
    raw_files = [path for path in raw_files if path.is_file()]
    if not raw_files:
        print(f"[index_weights_csv] 未找到 {dates[0]} 至 {dates[-1]} 的原始 JSON，CSV 不变", flush=True)
        return {"rows": 0, "replaced_rows": 0, "partitions": 0}
    deltas = []
    for raw_file in raw_files:
        with raw_file.open(encoding="utf-8") as stream:
            normalized = normalize_index_weights_response(
                json.load(stream), raw_file.stem, index_code
            )
        deltas.append({
            "date": raw_file.stem,
            **{str(row["thscode"]): row["weight"] for row in normalized},
        })
    temporary_path = output_path.with_suffix(".csv.tmp")
    with output_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or reader.fieldnames[0] != "date":
            print("[index_weights_csv] 现有 CSV 不是当前宽表结构，改为全量重建", flush=True)
            return build_index_weights_csv(output_root, index_code)
        existing_symbols = reader.fieldnames[1:]
        delta_dates = {str(delta["date"]) for delta in deltas}
        rows = [row for row in reader if row["date"] not in delta_dates]
    delta_symbols = set().union(*(set(delta) for delta in deltas))
    symbols = [*existing_symbols, *sorted(delta_symbols - {"date", *existing_symbols})]
    rows.extend(deltas)
    rows.sort(key=lambda row: str(row["date"]))
    _write_wide_csv(temporary_path, symbols, rows)
    temporary_path.replace(output_path)
    summary = {
        "rows": len(rows),
        "replaced_rows": len(deltas),
        "partitions": len(raw_files),
    }
    print(
        f"[index_weights_csv] 已完成区间更新：替换 {len(deltas)} 行，写入 {output_path}",
        flush=True,
    )
    return summary


def update_index_weights_csv(output_root: Path, index_code: str, as_of: str) -> dict[str, int]:
    return update_index_weights_csv_range(output_root, index_code, [as_of])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("rebuild", "update"), default="rebuild")
    parser.add_argument("--index", default="000300.SH")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of")
    args = parser.parse_args()
    if args.command == "update" and not args.as_of:
        raise SystemExit("update 必须提供 --as-of")
    result = update_index_weights_csv(args.output_root, args.index, args.as_of) if args.command == "update" else build_index_weights_csv(args.output_root, args.index)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
