"""将 iFinD 日期序列原始 JSON 汇总为完整 CSV，不调用 iFinD。"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from data_ingestion.ifind.date_sequence_download import SOURCE_FIELDS

CSV_FIELDS = ("float_mv", "pe", "pb", "industry_sw", "industry_sw_code", "limit_status")
FIELD_MAP = dict(zip(SOURCE_FIELDS, CSV_FIELDS, strict=True))
CSV_COLUMNS = ("date", "thscode", "exchange", *CSV_FIELDS, "source")


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


def build_date_sequence_csv(output_root: Path) -> dict[str, int]:
    raw_root = output_root / "date_sequence" / "raw"
    output_path = output_root / "date_sequence.csv"
    temporary_path = output_path.with_suffix(".csv.tmp")
    seen: set[tuple[str, str]] = set()
    summary = {"rows": 0, "partitions": 0}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with temporary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for path in sorted(raw_root.rglob("*.json")):
            exchange = path.relative_to(raw_root).parts[0]
            with path.open(encoding="utf-8") as raw_stream:
                rows = normalize_date_sequence_response(json.load(raw_stream), exchange)
            for row in sorted(rows, key=lambda item: (str(item["date"]), str(item["thscode"]))):
                key = (str(row["date"]), str(row["thscode"]))
                if key in seen:
                    raise ValueError(f"日期序列原始 JSON 存在重复 date + thscode：{key}")
                seen.add(key)
                writer.writerow(row)
                summary["rows"] += 1
            summary["partitions"] += 1
    temporary_path.replace(output_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[3] / "sources" / "ifind")
    args = parser.parse_args()
    print(json.dumps(build_date_sequence_csv(args.output_root), ensure_ascii=False))


if __name__ == "__main__":
    main()
