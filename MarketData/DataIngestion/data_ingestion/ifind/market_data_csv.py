"""将 iFinD 日频行情原始 JSON 汇总为完整 CSV，不调用 iFinD。"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from data_ingestion.ifind.market_data_download import LIQUIDITY, PRICE

DAILY_COLUMNS = ("date", "thscode", "exchange", "open", "high", "low", "close", "volume", "amount", "turnover", "adjustment", "source")


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


def build_daily_csv(output_root: Path) -> dict[str, int]:
    price_paths = _paths(output_root / "prices" / "hfq" / "raw")
    liquidity_paths = _paths(output_root / "liquidity" / "raw")
    output_path = output_root / "daily.csv"
    temporary_path = output_path.with_suffix(".csv.tmp")
    summary = {"rows": 0, "partitions": 0}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with temporary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=DAILY_COLUMNS)
        writer.writeheader()
        for relative in sorted(set(price_paths) | set(liquidity_paths), key=str):
            exchange = relative.parts[0]
            prices = _load(price_paths[relative], PRICE, exchange) if relative in price_paths else {}
            liquidity = _load(liquidity_paths[relative], LIQUIDITY, exchange) if relative in liquidity_paths else {}
            for key in sorted(set(prices) | set(liquidity)):
                price, liquid = prices.get(key, {}), liquidity.get(key, {})
                source = price or liquid
                writer.writerow({"date": source["date"], "thscode": source["thscode"], "exchange": source["exchange"], **{field: price.get(field, "") for field in ("open", "high", "low", "close", "adjustment")}, **{field: liquid.get(field, "") for field in ("volume", "amount", "turnover")}, "source": "ifind"})
                summary["rows"] += 1
            summary["partitions"] += 1
    temporary_path.replace(output_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[3] / "sources" / "ifind")
    args = parser.parse_args()
    print(json.dumps(build_daily_csv(args.output_root), ensure_ascii=False))


if __name__ == "__main__":
    main()
