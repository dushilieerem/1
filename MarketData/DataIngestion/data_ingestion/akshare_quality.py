"""AkShare 日线原始数据的发布前质量检查。"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path


REQUIRED_COLUMNS = {
    "symbol", "date", "open", "high", "low", "close", "amount", "change_ratio", "source",
}
OPTIONAL_COLUMNS = {"volume", "turn"}


def inspect_bars(
    bars_dir: Path,
    *,
    as_of: date,
    max_lag_days: int = 5,
) -> dict:
    """检查逐证券 CSV，并返回可序列化的质量报告。"""
    if max_lag_days < 0:
        raise ValueError("max_lag_days 不能小于 0")
    if not bars_dir.is_dir():
        raise FileNotFoundError(f"日线目录不存在：{bars_dir}")

    schema_counts: Counter[str] = Counter()
    missing_optional: Counter[str] = Counter()
    issues: list[dict] = []
    latest_dates: list[date] = []
    fresh = stale = 0

    for path in sorted(bars_dir.glob("*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            columns = set(reader.fieldnames or [])
            missing_required = sorted(REQUIRED_COLUMNS - columns)
            if missing_required:
                schema_counts[",".join(missing_required)] += 1
                issues.append({"path": path.name, "type": "missing_required", "columns": missing_required})
                continue

            for column in OPTIONAL_COLUMNS - columns:
                missing_optional[column] += 1

            previous: date | None = None
            seen_dates: set[date] = set()
            duplicate_dates = non_monotonic_dates = invalid_dates = 0
            last_date: date | None = None
            for row in reader:
                try:
                    current = date.fromisoformat(row["date"])
                except (TypeError, ValueError):
                    invalid_dates += 1
                    continue
                if current in seen_dates:
                    duplicate_dates += 1
                if previous is not None and current < previous:
                    non_monotonic_dates += 1
                seen_dates.add(current)
                previous = current
                last_date = current

            if last_date is None:
                issues.append({"path": path.name, "type": "empty_or_invalid_dates"})
                continue
            latest_dates.append(last_date)
            lag_days = (as_of - last_date).days
            if lag_days <= max_lag_days:
                fresh += 1
            else:
                stale += 1
                issues.append({"path": path.name, "type": "stale", "last_date": last_date.isoformat(), "lag_days": lag_days})
            if duplicate_dates or non_monotonic_dates or invalid_dates:
                issues.append({
                    "path": path.name,
                    "type": "date_integrity",
                    "duplicate_dates": duplicate_dates,
                    "non_monotonic_dates": non_monotonic_dates,
                    "invalid_dates": invalid_dates,
                })

    files = fresh + stale + sum(schema_counts.values()) + sum(
        1 for issue in issues if issue["type"] == "empty_or_invalid_dates"
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bars_dir": str(bars_dir),
        "as_of": as_of.isoformat(),
        "max_lag_days": max_lag_days,
        "file_count": files,
        "latest_date": max(latest_dates).isoformat() if latest_dates else None,
        "fresh_file_count": fresh,
        "stale_file_count": stale,
        "missing_required_columns": dict(schema_counts),
        "missing_optional_column_count": dict(missing_optional),
        "issue_count": len(issues),
        "issues": issues,
    }


def _parse_args() -> argparse.Namespace:
    market_data_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bars-dir",
        type=Path,
        default=market_data_root / "sources" / "akshare" / "03_market" / "daily" / "bars_hfq",
    )
    parser.add_argument("--as-of", required=True, help="质量评估基准日，格式 YYYY-MM-DD")
    parser.add_argument("--max-lag-days", type=int, default=5)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = inspect_bars(
        args.bars_dir,
        as_of=date.fromisoformat(args.as_of),
        max_lag_days=args.max_lag_days,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"已检查 {report['file_count']} 个文件："
        f"最新 {report['latest_date']}，新鲜 {report['fresh_file_count']}，"
        f"停更 {report['stale_file_count']}，问题 {report['issue_count']}"
    )


if __name__ == "__main__":
    main()
